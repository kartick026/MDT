"""Measured previews using one immutable-snapshot detector.

Default previews never write a database. The optional Neo4j research adapter
executes the same explicit mutations and always rolls its transaction back.
Graph-level improvements do not establish preserved application behavior.
"""
from __future__ import annotations
import asyncio
import math
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field, model_validator
from core.config import settings
from core.database import get_neo4j_driver, MockNeo4jDriver
from domain.architecture import (
    DETECTOR_VERSION, GraphSnapshot, configured_thresholds, detect_smells,
    registry_snapshot, snapshot_from_transaction,
)

MAX_PREVIEW_EDITS = 100
SATURATION_CONSTANT_K = 110.0 / 3.0
SCORE_TOLERANCE = 1e-9
SMELL_WEIGHTS = {
    "circular_dependency": 30, "shared_database": 20, "hub_and_spoke": 20,
    "bottleneck_service": 20, "dependency_explosion": 20, "high_coupling": 15,
    "api_instability": 15, "chatty_communication": 12,
    "missing_circuit_breaker": 12, "isolated_service": 5,
}
SMELL_KEYS = {
    "Circular Dependency": "circular_dependency", "Shared Database": "shared_database",
    "Hub-and-Spoke Centralization": "hub_and_spoke", "God / Bottleneck Service": "bottleneck_service",
    "Dependency Explosion": "dependency_explosion", "High Coupling": "high_coupling",
    "API Instability": "api_instability", "Chatty Communication": "chatty_communication",
    "Missing Circuit Breaker": "missing_circuit_breaker", "Dead / Isolated Service": "isolated_service",
}


class GraphEdit(BaseModel):
    """One explicit mutation; names carry no execution semantics."""
    model_config = ConfigDict(extra="forbid")
    action: Literal["remove_edge", "add_edge", "add_node", "update_node"]
    from_service: str = Field(min_length=1, max_length=200)
    to_service: Optional[str] = Field(default=None, min_length=1, max_length=200)
    relationship_type: Literal["DEPENDS_ON"] = "DEPENDS_ON"
    dependency_type: Optional[str] = Field(default=None, max_length=80)
    endpoint: Optional[str] = Field(default=None, max_length=2000)
    node_type: Literal["service", "database", "broker", "external"] = "service"
    has_circuit_breaker: Optional[bool] = None
    resilient: Optional[bool] = None

    @model_validator(mode="after")
    def validate_operation(self):
        if not self.from_service.strip() or (self.to_service is not None and not self.to_service.strip()):
            raise ValueError("Service names must not be whitespace")
        if self.action in {"remove_edge", "add_edge"} and self.to_service is None:
            raise ValueError("An edge edit requires from_service and to_service")
        if self.action in {"add_node", "update_node"} and self.to_service is not None:
            raise ValueError("Node edits must not specify to_service")
        if self.action == "update_node" and self.has_circuit_breaker is None and self.resilient is None:
            raise ValueError("update_node requires an explicit resilience property")
        if self.action in {"remove_edge", "add_edge"} and (self.has_circuit_breaker is not None or self.resilient is not None):
            raise ValueError("Use update_node for resilience properties")
        return self


def apply_snapshot_edits(snapshot: GraphSnapshot, edits: List[GraphEdit]) -> tuple[GraphSnapshot, list[dict]]:
    if len(edits) > MAX_PREVIEW_EDITS:
        raise ValueError(f"At most {MAX_PREVIEW_EDITS} edits may be previewed")
    data = snapshot.to_data()
    nodes = {s["name"]: s for s in data["services"]}
    edges, removed = data["dependencies"], []
    for edit in edits:
        src, dst = edit.from_service, edit.to_service
        if edit.action == "add_node":
            if src in nodes:
                raise ValueError(f"Service '{src}' already exists")
            nodes[src] = {"name": src, "node_type": edit.node_type,
                          "has_circuit_breaker": edit.has_circuit_breaker or False, "resilient": edit.resilient or False}
            continue
        if src not in nodes or (dst is not None and dst not in nodes):
            raise ValueError("Graph edit references an unknown service")
        if edit.action == "update_node":
            for key in ("has_circuit_breaker", "resilient"):
                if getattr(edit, key) is not None:
                    nodes[src][key] = getattr(edit, key)
            continue
        if edit.action == "add_edge":
            edge = {"from": src, "to": dst, "type": (edit.dependency_type or "http").lower(), "endpoint": edit.endpoint or ""}
            if any(all(existing.get(key) == value for key, value in edge.items()) for existing in edges):
                raise ValueError("Dependency edge already exists")
            edges.append(edge)
        else:
            matches = [e for e in edges if e["from"] == src and e["to"] == dst
                       and (edit.dependency_type is None or e["type"] == edit.dependency_type.lower())
                       and (edit.endpoint is None or e["endpoint"] == edit.endpoint)]
            if not matches:
                raise ValueError("Dependency edge does not exist")
            if len(matches) > 1:
                raise ValueError("Ambiguous dependency removal; specify dependency_type and endpoint")
            edges.remove(matches[0])
            removed.append(matches[0])
    data["services"] = list(nodes.values())
    return GraphSnapshot.from_data(data, source="preview_copy"), removed


def _apply_edits_on_tx(tx, edits: List[GraphEdit]) -> None:
    """Apply exactly the validated changes, without hidden rewiring."""
    for edit in edits:
        if edit.action == "add_node":
            tx.run("CREATE (s:Service {name: $name, node_type: $kind, has_circuit_breaker: $cb, resilient: $resilient})",
                   name=edit.from_service, kind=edit.node_type, cb=edit.has_circuit_breaker or False, resilient=edit.resilient or False).consume()
        elif edit.action == "update_node":
            props = {k: getattr(edit, k) for k in ("has_circuit_breaker", "resilient") if getattr(edit, k) is not None}
            tx.run("MATCH (s:Service {name: $name}) SET s += $props", name=edit.from_service, props=props).consume()
        elif edit.action == "add_edge":
            tx.run("MATCH (a:Service {name: $src}), (b:Service {name: $dst}) "
                   "CREATE (a)-[:DEPENDS_ON {type: $kind, endpoint: $endpoint}]->(b)",
                   src=edit.from_service, dst=edit.to_service, kind=(edit.dependency_type or "http").lower(), endpoint=edit.endpoint or "").consume()
        else:
            tx.run("MATCH (a:Service {name: $src})-[r:DEPENDS_ON]->(b:Service {name: $dst}) "
                   "WHERE ($kind IS NULL OR toLower(coalesce(r.type, 'http')) = $kind) "
                   "AND ($endpoint IS NULL OR coalesce(r.endpoint, '') = $endpoint) DELETE r",
                   src=edit.from_service, dst=edit.to_service,
                   kind=edit.dependency_type.lower() if edit.dependency_type else None, endpoint=edit.endpoint).consume()


def _count_smells_on_tx(tx) -> Dict[str, int]:
    return breakdown_smells(detect_smells(snapshot_from_transaction(tx), configured_thresholds()))


def _compute_uncapped_score_from_smells(smell_counts: Dict[str, int]) -> float:
    for count in smell_counts.values():
        if not isinstance(count, (int, float)) or not math.isfinite(count) or count < 0:
            raise ValueError("Smell counts must be finite and non-negative")
    return float(sum(smell_counts.get(key, 0) * weight for key, weight in SMELL_WEIGHTS.items()))


def _normalize_score(raw: float, k: float = SATURATION_CONSTANT_K) -> float:
    if not math.isfinite(raw) or raw < 0 or not math.isfinite(k) or k <= 0:
        raise ValueError("Debt must be finite and non-negative; normalization constant must be positive")
    return round(100.0 * raw / (raw + k), 3)


def _compute_score_from_smells(smell_counts: Dict[str, int]) -> float:
    return _normalize_score(_compute_uncapped_score_from_smells(smell_counts))


def _get_severity(score: float) -> str:
    if score >= settings.RISK_HIGH:
        return "CRITICAL"
    if score >= settings.RISK_MEDIUM:
        return "HIGH"
    if score >= settings.RISK_LOW:
        return "MEDIUM"
    return "LOW"


def compute_architecture_health(smell_counts: Dict[str, int], snapshot: GraphSnapshot | None = None) -> Dict[str, Any]:
    raw = _compute_uncapped_score_from_smells(smell_counts)
    score = _normalize_score(raw)
    result = {"score": score, "severity": _get_severity(score), "raw_score": raw,
            "total_smells": sum(smell_counts.values()), "smells": dict(smell_counts),
            "normalization_constant": SATURATION_CONSTANT_K, "detector_version": DETECTOR_VERSION,
            "weights": dict(SMELL_WEIGHTS)}
    if snapshot is not None:
        from domain.relations import is_startup, is_call
        data = snapshot.to_data()
        imported = data["project"].get("source") == "repository"
        edges = data["dependencies"]
        startup = sum(is_startup(edge) for edge in edges)
        calls = sum(is_call(edge) for edge in edges)
        result["evidence"] = {"startup_relations": startup, "static_or_modeled_calls": calls,
                              "configuration_relations": len(edges) - startup - calls,
                              "runtime_traffic_measured": False,
                              "unassessed_rules": (["runtime_isolation", "missing_resilience_without_explicit_evidence"] if imported else [])}
        result["assessment_status"] = ("insufficient_communication_evidence" if imported and len(edges) == startup
                                       else "partial" if imported else "modeled_graph")
        result["interpretation"] = ("Observed static findings only; zero does not establish a debt-free or safe architecture. "
                                    "Startup order is excluded; configuration references do not prove runtime calls.")
    return result


def breakdown_smells(smells: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = dict.fromkeys(SMELL_WEIGHTS, 0)
    for smell in smells:
        key = SMELL_KEYS.get(smell.get("type", ""))
        if key:
            counts[key] += 1
    return counts


def _calculate_simulation_metrics(before_smells, after_smells, edits) -> Tuple[float, float, float, bool, str]:
    before, after = compute_architecture_health(before_smells), compute_architecture_health(after_smells)
    raw_before, raw_after = before["raw_score"], after["raw_score"]
    exact_delta = 100 * raw_before / (raw_before + SATURATION_CONSTANT_K) - 100 * raw_after / (raw_after + SATURATION_CONSTANT_K)
    measurable = abs(exact_delta) > SCORE_TOLERANCE or before_smells != after_smells
    if exact_delta > SCORE_TOLERANCE:
        message = "Risk reduction verified for graph-level smells; application behavior is not verified."
    elif exact_delta < -SCORE_TOLERANCE:
        message = "Warning: Proposed edit increases architectural risk."
    elif measurable:
        message = "Tracked findings changed with no net architectural debt reduction."
    else:
        message = "No measurable change in tracked architectural smells"
    return before["score"], after["score"], round(before["score"] - after["score"], 3), measurable, message


def _find_best_remediation_target(exclude_service: str) -> str:
    data = registry_snapshot().to_data()
    names = [s["name"] for s in data["services"] if s["name"] != exclude_service and s["node_type"] == "service"]
    degree = {name: sum(name in (d["from"], d["to"]) for d in data["dependencies"]) for name in names}
    return min(names, key=lambda n: (-degree[n], n)) if names else ""


def generate_edits_for_smells(smells: List[Dict[str, Any]]) -> List[GraphEdit]:
    """Suggest explicit hypothetical changes; detection decides their effects."""
    data = registry_snapshot().to_data()
    from domain.relations import is_startup
    # Runtime/topology findings exclude deployment ordering. Rerouting startup
    # declarations as well both obscures the proposal and changes unrelated config.
    deps = [edge for edge in data["dependencies"] if not is_startup(edge)]
    names, edits = {s["name"] for s in data["services"]}, []

    def new_name(base):
        name, i = base, 2
        while name in names:
            name, i = f"{base}_{i}", i + 1
        names.add(name)
        return name

    def remove(edge):
        return GraphEdit(action="remove_edge", from_service=edge["from"], to_service=edge["to"],
                         dependency_type=edge["type"], endpoint=edge["endpoint"])

    for smell in smells:
        kind, services, evidence = smell.get("type", ""), smell.get("services", []), smell.get("evidence", {})
        if not services:
            continue
        target = services[0]
        if kind == "Circular Dependency":
            cycle = evidence.get("cycle") or (services + services[:1])
            if len(cycle) >= 2:
                matching = [d for d in deps if d["from"] == cycle[-2] and d["to"] == cycle[-1]]
                edits.extend([remove(d) for d in matching] or [GraphEdit(action="remove_edge", from_service=cycle[-2], to_service=cycle[-1])])
        elif kind == "Missing Circuit Breaker":
            edits.append(GraphEdit(action="update_node", from_service=target, has_circuit_breaker=True))
        elif kind in {"God / Bottleneck Service", "High Coupling"}:
            intermediary = new_name(f"{target}_facade" if "Bottleneck" in kind else f"{target}_gateway")
            edits.append(GraphEdit(action="add_node", from_service=intermediary))
            inbound = "Bottleneck" in kind
            matching = [d for d in deps if d["from"] != d["to"] and d["to" if inbound else "from"] == target]
            for d in matching:
                edits.append(remove(d))
                edits.append(GraphEdit(action="add_edge", from_service=d["from"] if inbound else intermediary,
                                       to_service=intermediary if inbound else d["to"], dependency_type=d["type"], endpoint=d["endpoint"]))
            edits.append(GraphEdit(action="add_edge", from_service=intermediary if inbound else target, to_service=target if inbound else intermediary))
        elif kind == "Shared Database" and evidence.get("shared_target") and len(services) >= 2:
            db, facade = evidence["shared_target"], new_name(f"{target}_data_facade")
            edits.append(GraphEdit(action="add_node", from_service=facade))
            edits.append(GraphEdit(action="add_edge", from_service=facade, to_service=db, dependency_type="database"))
            routed = set()
            for edge in deps:
                if edge["to"] == db and edge["from"] in services:
                    edits.append(remove(edge))
                    if edge["from"] not in routed:
                        edits.append(GraphEdit(action="add_edge", from_service=edge["from"], to_service=facade))
                        routed.add(edge["from"])
        elif kind == "Dead / Isolated Service":
            hub = _find_best_remediation_target(target)
            if hub:
                edits.append(GraphEdit(action="add_edge", from_service=hub, to_service=target))
        # Chatter, centralization and historical contracts need a design decision.
    return edits if len(edits) <= MAX_PREVIEW_EDITS else []


class RemediationSimulator:
    def __init__(self):
        self.driver = get_neo4j_driver()

    def _is_mock(self):
        return self.driver is None or isinstance(self.driver, MockNeo4jDriver) or getattr(self.driver, "is_mock", False)

    async def simulate_fix(self, edits: List[GraphEdit], baseline_risk_score: Optional[float] = None,
                           affected_files_count: Optional[int] = None, baseline_smells: Optional[Dict[str, int]] = None,
                           snapshot_version: Optional[str] = None, evaluation_mode: str = "snapshot") -> Dict[str, Any]:
        if evaluation_mode not in {"snapshot", "neo4j_transaction"}:
            raise ValueError("Unknown evaluation mode")
        snapshot = registry_snapshot()
        if snapshot_version and snapshot_version != snapshot.version:
            raise ValueError("Stale snapshot: refresh the architecture before previewing")
        if evaluation_mode == "neo4j_transaction":
            if self._is_mock():
                raise ValueError("A live Neo4j connection is required for transaction evaluation")
            return await self._simulate_live(edits, baseline_risk_score, affected_files_count, snapshot=snapshot)
        after, removed = apply_snapshot_edits(snapshot, edits)
        return self._result(snapshot, after, edits, removed, baseline_risk_score, affected_files_count, "snapshot")

    async def _simulate_mock(self, edits, baseline_risk_score=None, affected_files_count=None, baseline_smells=None):
        return await self.simulate_fix(edits, baseline_risk_score, affected_files_count)

    async def _simulate_live(self, edits, baseline_risk_score=None, affected_files_count=None, baseline_smells=None, snapshot=None):
        context = snapshot or registry_snapshot()
        def run():
            with self.driver.session() as session:
                tx = session.begin_transaction()
                try:
                    before = snapshot_from_transaction(tx, context)
                    if before.version != context.version:
                        raise ValueError("Stale Neo4j projection: refresh it before transaction evaluation")
                    expected, removed = apply_snapshot_edits(before, edits)
                    _apply_edits_on_tx(tx, edits)
                    after = snapshot_from_transaction(tx, context)
                    if after.version != expected.version:
                        raise ValueError("Transaction result does not match the requested graph edits")
                    return self._result(before, after, edits, removed, baseline_risk_score, affected_files_count, "neo4j_transaction")
                finally:
                    tx.rollback()
        return await asyncio.to_thread(run)

    @staticmethod
    def _result(before, after, edits, removed, baseline_risk_score, affected_files_count, mode):
        thresholds = configured_thresholds()
        before_findings, after_findings = detect_smells(before, thresholds), detect_smells(after, thresholds)
        before_counts, after_counts = breakdown_smells(before_findings), breakdown_smells(after_findings)
        before_health, after_health = compute_architecture_health(before_counts, before), compute_architecture_health(after_counts, after)
        _, _, reduction, measurable, message = _calculate_simulation_metrics(before_counts, after_counts, edits)
        before_ids, after_ids = {f["id"] for f in before_findings}, {f["id"] for f in after_findings}
        resolved = [f for f in before_findings if f["id"] not in after_ids]
        introduced = [f for f in after_findings if f["id"] not in before_ids]
        unchanged = [f for f in after_findings if f["id"] in before_ids]
        measurable = measurable or bool(resolved or introduced)
        raw_reduction = before_health["raw_score"] - after_health["raw_score"]
        if raw_reduction == 0 and (resolved or introduced):
            message = "Findings changed, but their weighted total is unchanged; no modeled debt improvement."
        score_explanation = []
        for kind, key in SMELL_KEYS.items():
            removed_count = sum(f["type"] == kind for f in resolved)
            added_count = sum(f["type"] == kind for f in introduced)
            if removed_count or added_count:
                score_explanation.append({"type": kind, "weight": SMELL_WEIGHTS[key],
                    "resolved": removed_count, "introduced": added_count,
                    "raw_debt_reduction": (removed_count - added_count) * SMELL_WEIGHTS[key]})
        commit_risk = None
        if baseline_risk_score is not None:
            if not math.isfinite(baseline_risk_score) or not 0 <= baseline_risk_score <= 100:
                raise ValueError("Commit risk must be between zero and 100")
            commit_risk = {"score": baseline_risk_score, "severity": _get_severity(baseline_risk_score),
                           "files_count": affected_files_count,
                           "message": "Commit risk is supplied context, not recomputed by this graph preview."}
        return {
            "before": before_health, "after": after_health,
            "delta": {"score_reduction": reduction, "raw_debt_reduction": raw_reduction,
                      "smells_resolved": len(resolved), "smells_introduced": len(introduced), "measurable_change": measurable, "message": message},
            "outcome": "improved" if raw_reduction > 0 else "worse" if raw_reduction < 0 else "unchanged",
            "score_explanation": score_explanation,
            "findings": {"resolved": resolved, "introduced": introduced, "unchanged": unchanged},
            "removed_dependencies": removed, "commit_risk": commit_risk, "sandbox": True,
            "measurable_change": measurable, "snapshot_version": before.version, "preview_snapshot_version": after.version,
            "detector_version": DETECTOR_VERSION, "evaluation_mode": mode, "thresholds": thresholds,
            "metric": "Architectural Smell Risk", "description": "Measured graph-level architectural debt; runtime behavior is not verified.",
            "provenance": {"source": before.source, "baseline": "server_recomputed", "historical_findings": "held_constant",
                           "cycle_max_nodes": 8, "numeric_tolerance": SCORE_TOLERANCE},
            "warnings": (["Removed dependencies may break functional behavior; validate application contracts."] if removed else [])
                        + (["Resilience properties are hypothetical; runtime circuit breakers are not verified."]
                           if any(e.has_circuit_breaker or e.resilient for e in edits) else []),
        }
