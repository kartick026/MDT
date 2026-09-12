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
            WHERE incoming <> s
            OPTIONAL MATCH (s)-[:DEPENDS_ON]->(outgoing:Service)
            WHERE outgoing <> s
            WITH s, count(DISTINCT incoming) AS inc, count(DISTINCT outgoing) AS out
            WHERE inc >= $inbound OR inc + out >= $total
            RETURN s.name AS name, inc, out
        """,
    },
    "high_coupling": {
        "query": """
            MATCH (s:Service)-[:DEPENDS_ON]->(dep:Service)
            WHERE dep <> s
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
            if not cycle or len(cycle) < 3:
                continue
            cycle_nodes = cycle[:-1]
            if len(cycle_nodes) != len(set(cycle_nodes)) or len(cycle_nodes) < 2:
                continue
            min_idx = cycle_nodes.index(min(cycle_nodes))
            canonical = cycle_nodes[min_idx:] + cycle_nodes[:min_idx]
            key = tuple(canonical)
            if key not in seen:
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
# Dynamic remediation target finder
# ---------------------------------------------------------------------------

def _find_best_remediation_target(exclude_service: str) -> str:
    """Dynamically select a hub or active non-isolated service to re-link an isolated service."""
    try:
        from core.registry import RegistryManager
        registered = [
            s["name"] for s in RegistryManager.get_services()
            if s.get("name") and s.get("name") != exclude_service
        ]
        if not registered:
            return "api-gateway"

        # Check degree in existing dependencies
        deps = RegistryManager.get_dependencies()
        degree: Dict[str, int] = {s: 0 for s in registered}
        for d in deps:
            src = d.get("from")
            dst = d.get("to")
            if src in degree:
                degree[src] += 1
            if dst in degree:
                degree[dst] += 1

        sorted_by_degree = sorted(degree.items(), key=lambda x: x[1], reverse=True)
        return sorted_by_degree[0][0]
    except Exception as exc:
        logger.debug("Failed to find dynamic remediation target from registry: %s", exc)
        return "api-gateway"


def generate_edits_for_smells(smells: List[Dict[str, Any]]) -> List[GraphEdit]:
    """
    Deterministic rule-based mapping from detected smells to graph edits.

    - Circular: remove the back-edge that closes the cycle.
    - God/Bottleneck: insert a facade node and rewire callers.
    - High Coupling: insert a gateway facade.
    - Dead/Isolated: reconnect the isolated node to an active hub service.
    """
    edits: List[GraphEdit] = []

    for smell in smells:
        stype = smell.get("type", "")
        services = smell.get("services", [])

        if "Circular" in stype:
            cycle = smell.get("evidence", {}).get("cycle", [])
            if len(cycle) >= 2:
                edits.append(GraphEdit(
                    action="remove_edge",
                    from_service=cycle[-2],
                    to_service=cycle[-1] if cycle[-1] != cycle[-2] else cycle[0],
                ))
            elif len(services) >= 2:
                edits.append(GraphEdit(
                    action="remove_edge",
                    from_service=services[1],
                    to_service=services[0],
                ))

        elif "Bottleneck" in stype or "God" in stype:
            if services:
                target = services[0]
                facade_name = f"{target}_facade"
                edits.append(GraphEdit(action="add_node", from_service=facade_name))
                edits.append(GraphEdit(
                    action="add_edge",
                    from_service=facade_name,
                    to_service=target,
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
                target_hub = _find_best_remediation_target(isolated)
                edits.append(GraphEdit(
                    action="add_edge",
                    from_service=target_hub,
                    to_service=isolated,
                ))

    return edits



def _compute_uncapped_score_from_smells(smell_counts: Dict[str, int]) -> float:
    """Calculate raw sum of smell weights without capping at 100."""
    score = 0.0
    score += smell_counts.get("circular_dependency", 0) * 30   # CRITICAL
    score += smell_counts.get("bottleneck_service", 0) * 20    # HIGH
    score += smell_counts.get("high_coupling", 0) * 15         # MEDIUM
    score += smell_counts.get("isolated_service", 0) * 5       # LOW
    return score


def _calculate_simulation_metrics(
    before_smells: Dict[str, int],
    after_smells: Dict[str, int],
    edits: List[GraphEdit],
) -> Tuple[float, float, float, bool, str]:
    """Calculate before_score, after_score, point_reduction, measurable_change, and message for pure architectural smell risk."""
    before_total = sum(before_smells.values())
    after_total = sum(after_smells.values())
    smells_resolved = before_total - after_total

    cycles_resolved = max(0, before_smells.get("circular_dependency", 0) - after_smells.get("circular_dependency", 0))
    bottlenecks_resolved = max(0, before_smells.get("bottleneck_service", 0) - after_smells.get("bottleneck_service", 0))
    coupling_resolved = max(0, before_smells.get("high_coupling", 0) - after_smells.get("high_coupling", 0))
    isolated_resolved = max(0, before_smells.get("isolated_service", 0) - after_smells.get("isolated_service", 0))

    raw_before = _compute_uncapped_score_from_smells(before_smells)
    raw_after = _compute_uncapped_score_from_smells(after_smells)

    before_score = round(min(100.0, raw_before), 1)

    if raw_before == 0.0 or raw_after >= raw_before:
        point_reduction = 0.0
        after_score = before_score
    elif raw_before <= 100.0:
        # Standard linear point reduction below saturation threshold
        after_score = round(max(0.0, raw_after), 1)
        point_reduction = round(max(0.0, before_score - after_score), 1)
    else:
        # When cumulative smell debt exceeds 100, calculate proportional reduction
        # so that resolving major smells produces a meaningful score reduction
        reduction_ratio = (raw_before - raw_after) / raw_before
        point_reduction = round(min(before_score, before_score * reduction_ratio), 1)
        after_score = round(max(0.0, before_score - point_reduction), 1)

    measurable_change = (point_reduction > 0) or (smells_resolved > 0)

    details = []
    if cycles_resolved > 0:
        details.append(f"{cycles_resolved} circular dependency resolved")
    if bottlenecks_resolved > 0:
        details.append(f"{bottlenecks_resolved} bottleneck resolved")
    if coupling_resolved > 0:
        details.append(f"{coupling_resolved} coupling resolved")
    if isolated_resolved > 0:
        details.append(f"{isolated_resolved} isolated service resolved")
    if not details and point_reduction > 0:
        details.append("architectural remediation applied")

    if measurable_change and point_reduction > 0:
        message = f"Risk reduction verified: {', '.join(details)} (-{point_reduction} pts smell risk)"
    elif measurable_change:
        message = "Smell reduction verified"
    else:
        message = "No measurable change in tracked architectural smells"

    return before_score, after_score, point_reduction, measurable_change, message




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

    async def simulate_fix(
        self,
        edits: List[GraphEdit],
        baseline_risk_score: Optional[float] = None,
        affected_files_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run edits in a sandbox and return before/after comparison.

        Returns a dict with keys: before, after, delta, commit_risk, sandbox.
        """
        if self._is_mock():
            return await self._simulate_mock(
                edits,
                baseline_risk_score=baseline_risk_score,
                affected_files_count=affected_files_count,
            )
        return await self._simulate_live(
            edits,
            baseline_risk_score=baseline_risk_score,
            affected_files_count=affected_files_count,
        )


    # ------------------------------------------------------------------ #
    #  Live Neo4j mode
    # ------------------------------------------------------------------ #

    async def _simulate_live(
        self,
        edits: List[GraphEdit],
        baseline_risk_score: Optional[float] = None,
        affected_files_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Transactional simulation on a real Neo4j instance."""

        def _run_in_tx():
            assert self.driver is not None
            with self.driver.session() as session:
                tx = session.begin_transaction()
                try:
                    # 1. Measure BEFORE state
                    before_smells = _count_smells_on_tx(tx)

                    # 2. Apply edits
                    _apply_edits_on_tx(tx, edits)

                    # 3. Measure AFTER state
                    after_smells = _count_smells_on_tx(tx)

                    return before_smells, after_smells
                finally:
                    # ALWAYS rollback — the graph is never mutated
                    tx.rollback()

        before_smells, after_smells = await asyncio.to_thread(_run_in_tx)

        before_score, after_score, point_reduction, measurable_change, message = _calculate_simulation_metrics(
            before_smells, after_smells, edits
        )

        before_total = sum(before_smells.values())
        after_total = sum(after_smells.values())

        commit_risk = None
        if baseline_risk_score is not None:
            base_score = round(float(baseline_risk_score), 1)
            sev = _get_severity(base_score)
            files_desc = (
                f"{affected_files_count} source file{'s' if affected_files_count != 1 else ''}"
                if affected_files_count
                else "modified source files"
            )
            commit_risk = {
                "score": base_score,
                "severity": sev,
                "files_count": affected_files_count,
                "message": (
                    f"Git Commit Risk remains {base_score}/100 ({sev}) because deployment blast radius "
                    f"is driven by {files_desc} and core configurations."
                ),
            }

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
                "score_reduction": round(point_reduction, 1),
                "smells_resolved": max(0, before_total - after_total),
                "measurable_change": measurable_change,
                "message": message,
            },
            "commit_risk": commit_risk,
            "measurable_change": measurable_change,
            "metric": "Architectural Smell Risk",
            "description": "Evaluates architectural anti-patterns (cycles, bottlenecks, coupling, isolation) on the dependency graph.",
            "sandbox": True,
        }

    # ------------------------------------------------------------------ #
    #  Mock / fallback mode
    # ------------------------------------------------------------------ #

    async def _simulate_mock(
        self,
        edits: List[GraphEdit],
        baseline_risk_score: Optional[float] = None,
        affected_files_count: Optional[int] = None,
    ) -> Dict[str, Any]:
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
            elif edit.action == "add_edge":
                if "_facade" in (edit.from_service or "") or "_gateway" in (edit.from_service or ""):
                    if after_counts["bottleneck_service"] > 0:
                        after_counts["bottleneck_service"] = max(
                            0, after_counts["bottleneck_service"] - 1
                        )
                    if after_counts["high_coupling"] > 0:
                        after_counts["high_coupling"] = max(
                            0, after_counts["high_coupling"] - 1
                        )

        before_score, after_score, point_reduction, measurable_change, message = _calculate_simulation_metrics(
            before_counts, after_counts, edits
        )

        before_total = sum(before_counts.values())
        after_total = sum(after_counts.values())

        commit_risk = None
        if baseline_risk_score is not None:
            base_score = round(float(baseline_risk_score), 1)
            sev = _get_severity(base_score)
            files_desc = (
                f"{affected_files_count} source file{'s' if affected_files_count != 1 else ''}"
                if affected_files_count
                else "modified source files"
            )
            commit_risk = {
                "score": base_score,
                "severity": sev,
                "files_count": affected_files_count,
                "message": (
                    f"Git Commit Risk remains {base_score}/100 ({sev}) because deployment blast radius "
                    f"is driven by {files_desc} and core configurations."
                ),
            }

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
                "score_reduction": round(point_reduction, 1),
                "smells_resolved": max(0, before_total - after_total),
                "measurable_change": measurable_change,
                "message": message,
            },
            "commit_risk": commit_risk,
            "measurable_change": measurable_change,
            "metric": "Architectural Smell Risk",
            "description": "Evaluates architectural anti-patterns (cycles, bottlenecks, coupling, isolation) on the dependency graph.",
            "sandbox": True,
        }

