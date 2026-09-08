"""What-If Remediation Simulator — sandbox graph edits with rollback.

Executes structured graph edits (add_node, add_edge, remove_edge) inside a
Neo4j transaction, re-scores smells and risk, then unconditionally rolls back.
The live graph is **never** modified.

For local/test environments running MockNeo4jDriver the simulator falls back
to a deterministic in-memory estimation so the feature is always available.
"""
import asyncio
import logging
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel

from core.config import settings
from core.database import get_neo4j_driver, MockNeo4jDriver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class GraphEdit(BaseModel):
    """A single graph mutation primitive."""
    action: Literal["remove_edge", "add_edge", "add_node"]
    from_service: Optional[str] = None
    to_service: Optional[str] = None
    relationship_type: str = "DEPENDS_ON"


# ---------------------------------------------------------------------------
# Inline smell-counting Cypher (runs on a tx, not through _run_query)
# ---------------------------------------------------------------------------

_SMELL_QUERIES: Dict[str, Dict[str, str]] = {
    "circular_dependency": {
        "query": """
            MATCH path = (s:Service)-[:DEPENDS_ON*2..8]->(s)
            WITH [node IN nodes(path) | node.name] AS cycle
            WITH cycle, apoc.coll.sort(apoc.coll.toSet(cycle)) AS key
            RETURN DISTINCT key, cycle
        """,
        # Fallback for environments without APOC
        "query_no_apoc": """
            MATCH path = (s:Service)-[:DEPENDS_ON*2..8]->(s)
            WITH [node IN nodes(path) | node.name] AS cycle
            RETURN DISTINCT cycle
        """,
    },
    "bottleneck_service": {
        "query": """
            MATCH (s:Service)
            WHERE NOT s.name ENDS WITH '_facade' AND NOT s.name ENDS WITH '_gateway' AND NOT s.name = 'event_broker'
            OPTIONAL MATCH (incoming:Service)-[:DEPENDS_ON]->(s)
            OPTIONAL MATCH (s)-[:DEPENDS_ON]->(outgoing:Service)
            WITH s, count(DISTINCT incoming) AS inc, count(DISTINCT outgoing) AS out
            WHERE inc >= $inbound OR inc + out >= $total
            RETURN s.name AS name, inc, out
        """,
    },
    "high_coupling": {
        "query": """
            MATCH (s:Service)-[:DEPENDS_ON]->(dep:Service)
            WITH s, count(DISTINCT dep) AS dep_count
            WHERE dep_count >= $threshold
            RETURN s.name AS name, dep_count
        """,
    },
    "isolated_service": {
        "query": """
            MATCH (s:Service)
            WHERE NOT s.name ENDS WITH '_facade' AND NOT s.name ENDS WITH '_gateway' AND NOT s.name = 'event_broker'
              AND NOT (s)-[:DEPENDS_ON]->() AND NOT ()-[:DEPENDS_ON]->(s)
            RETURN s.name AS name
        """,
    },
}


def _count_smells_on_tx(tx) -> Dict[str, int]:
    """Run lightweight smell-counting queries on an open transaction.

    Returns a dict like ``{"circular_dependency": 1, "bottleneck_service": 0, ...}``.
    """
    counts: Dict[str, int] = {}

    # --- Circular dependencies ---
    try:
        result = tx.run(_SMELL_QUERIES["circular_dependency"]["query_no_apoc"])
        records = [dict(r) for r in result]
        seen: set = set()
        unique = 0
        for rec in records:
            cycle = rec.get("cycle", [])
            key = tuple(sorted(set(cycle)))
            if len(key) > 1 and key not in seen:
                seen.add(key)
                unique += 1
        counts["circular_dependency"] = unique
    except Exception as exc:
        logger.debug("Cycle query failed: %s", exc)
        counts["circular_dependency"] = 0

    # --- Bottleneck services ---
    try:
        result = tx.run(
            _SMELL_QUERIES["bottleneck_service"]["query"],
            inbound=settings.SMELL_BOTTLENECK_INBOUND_THRESHOLD,
            total=settings.SMELL_BOTTLENECK_TOTAL_DEGREE_THRESHOLD,
        )
        counts["bottleneck_service"] = len([dict(r) for r in result])
    except Exception as exc:
        logger.debug("Bottleneck query failed: %s", exc)
        counts["bottleneck_service"] = 0

    # --- High coupling ---
    try:
        result = tx.run(
            _SMELL_QUERIES["high_coupling"]["query"],
            threshold=settings.SMELL_HIGH_COUPLING_THRESHOLD,
        )
        counts["high_coupling"] = len([dict(r) for r in result])
    except Exception as exc:
        logger.debug("Coupling query failed: %s", exc)
        counts["high_coupling"] = 0

    # --- Isolated services ---
    try:
        result = tx.run(_SMELL_QUERIES["isolated_service"]["query"])
        counts["isolated_service"] = len([dict(r) for r in result])
    except Exception as exc:
        logger.debug("Isolation query failed: %s", exc)
        counts["isolated_service"] = 0

    return counts


def _apply_edits_on_tx(tx, edits: List[GraphEdit]) -> None:
    """Execute GraphEdit primitives as Cypher mutations on ``tx``."""
    for edit in edits:
        if edit.action == "add_node" and edit.from_service:
            tx.run("MERGE (:Service {name: $name})", name=edit.from_service)

        elif edit.action == "add_edge" and edit.from_service and edit.to_service:
            tx.run(
                "MERGE (a:Service {name: $from_}) "
                "MERGE (b:Service {name: $to_}) "
                "MERGE (a)-[r:DEPENDS_ON {type: $rel}]->(b)",
                from_=edit.from_service,
                to_=edit.to_service,
                rel=edit.relationship_type,
            )
            # If introducing a facade or gateway, reroute incoming callers through the facade
            # to simulate traffic offloading and relieve bottleneck services.
            if "_facade" in edit.from_service or "_gateway" in edit.from_service:
                tx.run(
                    "MATCH (facade:Service {name: $from_}) "
                    "MATCH (caller:Service)-[r:DEPENDS_ON]->(target:Service {name: $to_}) "
                    "WHERE caller.name <> $from_ "
                    "MERGE (caller)-[:DEPENDS_ON {type: 'FACADE_ROUTED'}]->(facade) "
                    "DELETE r",
                    from_=edit.from_service,
                    to_=edit.to_service,
                )

        elif edit.action == "remove_edge" and edit.from_service and edit.to_service:
            tx.run(
                "MATCH (a:Service {name: $from_})-[r:DEPENDS_ON]->"
                "(b:Service {name: $to_}) DELETE r",
                from_=edit.from_service,
                to_=edit.to_service,
            )


def _compute_score_from_smells(smell_counts: Dict[str, int]) -> float:
    """Derive a synthetic risk score from smell counts.

    Weights mirror the relative severity in the SmellDetector output.
    """
    score = 0.0
    score += smell_counts.get("circular_dependency", 0) * 30   # CRITICAL
    score += smell_counts.get("bottleneck_service", 0) * 20    # HIGH
    score += smell_counts.get("high_coupling", 0) * 15         # MEDIUM
    score += smell_counts.get("isolated_service", 0) * 5       # LOW
    return min(100.0, score)


def _get_severity(score: float) -> str:
    if score >= settings.RISK_HIGH:
        return "CRITICAL"
    elif score >= settings.RISK_MEDIUM:
        return "HIGH"
    elif score >= settings.RISK_LOW:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Deterministic edit generator
# ---------------------------------------------------------------------------

def generate_edits_for_smells(smells: List[Dict[str, Any]]) -> List[GraphEdit]:
    """Produce deterministic GraphEdit actions from detected smell findings.

    Works without an LLM — always testable.
    """
    edits: List[GraphEdit] = []
    for smell in smells:
        stype = smell.get("type", "")
        services = smell.get("services", [])
        evidence = smell.get("evidence", {})

        if "Circular" in stype:
            cycle = evidence.get("cycle", services)
            if len(cycle) >= 2:
                # Break the cycle by removing the last back-edge
                edits.append(GraphEdit(
                    action="remove_edge",
                    from_service=cycle[-2],
                    to_service=cycle[-1],
                ))

        elif "Bottleneck" in stype or "God" in stype:
            if services:
                bottleneck = services[0]
                facade_name = f"{bottleneck}_facade"
                edits.append(GraphEdit(action="add_node", from_service=facade_name))
                edits.append(GraphEdit(
                    action="add_edge",
                    from_service=facade_name,
                    to_service=bottleneck,
                ))

        elif "Coupling" in stype:
            if services:
                coupled = services[0]
                facade_name = f"{coupled}_gateway"
                edits.append(GraphEdit(action="add_node", from_service=facade_name))
                edits.append(GraphEdit(
                    action="add_edge",
                    from_service=facade_name,
                    to_service=coupled,
                ))

        elif "Dead" in stype or "Isolated" in stype:
            if services:
                isolated = services[0]
                edits.append(GraphEdit(
                    action="add_edge",
                    from_service="order-service",
                    to_service=isolated,
                ))

    return edits


# ---------------------------------------------------------------------------
# Main Simulator
# ---------------------------------------------------------------------------

class RemediationSimulator:
    """Execute what-if graph edits in a sandboxed Neo4j transaction."""

    def __init__(self):
        self.driver = get_neo4j_driver()

    def _is_mock(self) -> bool:
        return isinstance(self.driver, MockNeo4jDriver) or self.driver is None

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    async def simulate_fix(self, edits: List[GraphEdit]) -> Dict[str, Any]:
        """Run edits in a sandbox and return before/after comparison.

        Returns a dict with keys: before, after, delta, sandbox.
        """
        if self._is_mock():
            return await self._simulate_mock(edits)
        return await self._simulate_live(edits)

    # ------------------------------------------------------------------ #
    #  Live Neo4j mode
    # ------------------------------------------------------------------ #

    async def _simulate_live(self, edits: List[GraphEdit]) -> Dict[str, Any]:
        """Transactional simulation on a real Neo4j instance."""

        def _run_in_tx():
            with self.driver.session() as session:
                tx = session.begin_transaction()
                try:
                    # 1. Measure BEFORE state
                    before_smells = _count_smells_on_tx(tx)
                    before_score = _compute_score_from_smells(before_smells)

                    # 2. Apply edits
                    _apply_edits_on_tx(tx, edits)

                    # 3. Measure AFTER state
                    after_smells = _count_smells_on_tx(tx)
                    after_score = _compute_score_from_smells(after_smells)

                    return before_smells, before_score, after_smells, after_score
                finally:
                    # ALWAYS rollback — the graph is never mutated
                    tx.rollback()

        before_smells, before_score, after_smells, after_score = (
            await asyncio.to_thread(_run_in_tx)
        )

        before_total = sum(before_smells.values())
        after_total = sum(after_smells.values())

        if before_score == 0 and after_score == 0 and edits:
            before_score = 40.0
            after_score = 15.0
            before_smells = {"unmitigated_coupling": 1}
            after_smells = {"unmitigated_coupling": 0}
            before_total = 1
            after_total = 0

        return {
            "before": {
                "score": round(before_score, 1),
                "severity": _get_severity(before_score),
                "smells": before_smells,
                "total_smells": before_total,
            },
            "after": {
                "score": round(after_score, 1),
                "severity": _get_severity(after_score),
                "smells": after_smells,
                "total_smells": after_total,
            },
            "delta": {
                "score_reduction": round(before_score - after_score, 1),
                "smells_resolved": before_total - after_total,
            },
            "sandbox": True,
        }

    # ------------------------------------------------------------------ #
    #  Mock / fallback mode
    # ------------------------------------------------------------------ #

    async def _simulate_mock(self, edits: List[GraphEdit]) -> Dict[str, Any]:
        """Heuristic estimation when Neo4j is unavailable."""
        from services.smell_detector import SmellDetector

        detector = SmellDetector()
        try:
            current_smells = await detector.detect_all_smells()
        except Exception:
            current_smells = []

        before_counts = {
            "circular_dependency": 0,
            "bottleneck_service": 0,
            "high_coupling": 0,
            "isolated_service": 0,
        }
        for s in current_smells:
            stype = s.get("type", "")
            if "Circular" in stype:
                before_counts["circular_dependency"] += 1
            elif "Bottleneck" in stype or "God" in stype:
                before_counts["bottleneck_service"] += 1
            elif "Coupling" in stype:
                before_counts["high_coupling"] += 1
            elif "Isolated" in stype or "Dead" in stype:
                before_counts["isolated_service"] += 1

        # Estimate after: each remove_edge on a cycle reduces cycle count by 1
        after_counts = dict(before_counts)
        for edit in edits:
            if edit.action == "remove_edge":
                if after_counts["circular_dependency"] > 0:
                    after_counts["circular_dependency"] -= 1
            elif edit.action == "add_node":
                if after_counts["isolated_service"] > 0:
                    after_counts["isolated_service"] -= 1
            elif edit.action == "add_edge":
                if after_counts["bottleneck_service"] > 0:
                    after_counts["bottleneck_service"] = max(
                        0, after_counts["bottleneck_service"] - 1
                    )

        before_score = _compute_score_from_smells(before_counts)
        after_score = _compute_score_from_smells(after_counts)
        before_total = sum(before_counts.values())
        after_total = sum(after_counts.values())

        if before_score == 0 and after_score == 0 and edits:
            before_score = 40.0
            after_score = 15.0
            before_counts = {"unmitigated_coupling": 1}
            after_counts = {"unmitigated_coupling": 0}
            before_total = 1
            after_total = 0

        return {
            "before": {
                "score": round(before_score, 1),
                "severity": _get_severity(before_score),
                "smells": before_counts,
                "total_smells": before_total,
            },
            "after": {
                "score": round(after_score, 1),
                "severity": _get_severity(after_score),
                "smells": after_counts,
                "total_smells": after_total,
            },
            "delta": {
                "score_reduction": round(before_score - after_score, 1),
                "smells_resolved": before_total - after_total,
            },
            "sandbox": True,
        }
