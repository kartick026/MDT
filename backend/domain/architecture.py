"""Versioned architecture snapshots and one detector implementation.

No database, network, registry writes or naming conventions affect evaluation.
The depth limit is explicit: elementary dependency cycles up to eight nodes.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from domain.relations import is_startup, is_call

DETECTOR_VERSION = "2.1.0"
MAX_GRAPH_NODES = 500
MAX_GRAPH_EDGES = 5000
MAX_CYCLE_SEARCH_STEPS = 100000
DATABASE_TYPES = {"database", "db", "sql", "postgres", "postgresql", "mysql", "mongodb", "redis"}


def normalize_api_endpoints(service: dict[str, Any]) -> list[dict[str, Any]]:
    """Preserve captured contracts without inventing an HTTP method for old paths."""
    endpoints = service.get("api_endpoints", service.get("endpoints", [])) or []
    normalized = {}
    for endpoint in endpoints:
        if isinstance(endpoint, str):
            parts = endpoint.strip().split(" ", 1)
            endpoint = ({"method": parts[0], "path": parts[1]} if len(parts) == 2 and parts[0].upper() in
                        {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"}
                        else {"method": "UNKNOWN", "path": endpoint})
        if not isinstance(endpoint, dict) or not endpoint.get("path"):
            continue
        contract = {"method": str(endpoint.get("method") or "UNKNOWN").upper(), "path": str(endpoint["path"])}
        for key in ("parameters", "request_schema", "response_schema", "responses", "request_body", "response_model", "status_code", "security"):
            if key in endpoint:
                contract[key] = copy.deepcopy(endpoint[key])
        encoded = json.dumps(contract, sort_keys=True, separators=(",", ":"))
        normalized[encoded] = contract
    return [normalized[key] for key in sorted(normalized)]


def circuit_breaker_threshold(total: int, outbound_counts: list[int] | None = None) -> int:
    threshold = max(2, math.ceil(math.sqrt(max(0, total))))
    if outbound_counts and len(outbound_counts) > 1:
        mean = sum(outbound_counts) / len(outbound_counts)
        std = math.sqrt(sum((x - mean) ** 2 for x in outbound_counts) / len(outbound_counts))
        threshold = min(threshold, max(2, math.ceil(mean + std)))
    return threshold


def hub_threshold(total: int) -> int:
    if total < 3:
        return 0
    return max(2, math.ceil(min(.85, max(.60, 1 - 1 / math.sqrt(total))) * (total - 1)))


@dataclass(frozen=True)
class GraphSnapshot:
    """Owned copies of graph data; callers obtain mutable copies via to_data()."""
    _json: str
    version: str
    source: str = "registry"

    @classmethod
    def from_data(cls, data: dict[str, Any], source: str = "registry") -> "GraphSnapshot":
        imported = data.get("project", {}).get("source") == "repository"
        services = {}
        for item in data.get("services", []):
            name = item.get("name")
            if name:
                services[name] = {
                    "name": name,
                    "node_type": item.get("node_type") or ("external" if item.get("is_external") else "service"),
                    "has_circuit_breaker": item.get("has_circuit_breaker", None if imported else False),
                    "resilient": item.get("resilient", None if imported else False),
                }
                # Contract-only changes must produce a distinct snapshot version.
                # Omit absent contracts so existing graph-only fixtures stay stable.
                if "api_endpoints" in item or "endpoints" in item:
                    services[name]["api_endpoints"] = normalize_api_endpoints(item)
        dependencies = {}
        for item in data.get("dependencies", []):
            src, dst = item.get("from"), item.get("to")
            if not src or not dst:
                continue
            kind = str(item.get("type") or "http").lower()
            endpoint = str(item.get("endpoint") or "")
            edge = {"from": src, "to": dst, "type": kind, "endpoint": endpoint}
            for key in ("evidence_kind", "source_file", "source_line", "environment_variable", "method"):
                if item.get(key) is not None:
                    edge[key] = copy.deepcopy(item[key])
            key = (src, dst, kind, endpoint, str(item.get("method") or ""))
            previous = dependencies.get(key)
            if previous is None or not is_call(previous) or is_call(edge):
                dependencies[key] = edge
            for name in (src, dst):
                services.setdefault(name, {"name": name, "node_type": "external", "has_circuit_breaker": False, "resilient": False})
            # Compatibility adapter: typed database edges establish resource type;
            # a service's spelling must never change detector behavior.
            if kind in DATABASE_TYPES:
                services[dst]["node_type"] = "database"
        if len(services) > MAX_GRAPH_NODES or len(dependencies) > MAX_GRAPH_EDGES:
            raise ValueError(f"Graph exceeds preview limits ({MAX_GRAPH_NODES} nodes / {MAX_GRAPH_EDGES} edges)")
        normalized = {
            "services": sorted(services.values(), key=lambda s: s["name"]),
            "dependencies": [dependencies[key] for key in sorted(dependencies)],
            "dependency_snapshots": copy.deepcopy(data.get("dependency_snapshots") or data.get("snapshots") or []),
            "api_snapshots": copy.deepcopy(data.get("api_snapshots") or []),
            "project": copy.deepcopy(data.get("project") or {}),
            "file_mappings": copy.deepcopy(data.get("file_mappings") or {}),
            "coverage": copy.deepcopy(data.get("coverage") or {}),
        }
        encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return cls(encoded, hashlib.sha256(encoded.encode()).hexdigest(), source)

    def to_data(self) -> dict[str, Any]:
        return json.loads(self._json)


def registry_snapshot() -> GraphSnapshot:
    from core.registry import RegistryManager
    data = RegistryManager.load()
    # Getters keep compatibility with adapters that provide scoped registries.
    data["services"] = RegistryManager.get_services()
    data["dependencies"] = RegistryManager.get_dependencies()
    data["project"] = RegistryManager.get_project_context()
    if data["project"].get("source") == "local_demo":
        history = RegistryManager.get_local_demo_smell_history()
        for key in ("dependency_snapshots", "api_snapshots"):
            if not data.get(key):
                data[key] = history.get(key, [])
    return GraphSnapshot.from_data(data)


def snapshot_from_transaction(tx, context: GraphSnapshot | None = None) -> GraphSnapshot:
    """Read nodes and edges together; history remains immutable experiment context."""
    record = tx.run("""
        MATCH (s:Service)
        WITH collect(properties(s)) AS services
        OPTIONAL MATCH (a:Service)-[r:DEPENDS_ON]->(b:Service)
        RETURN services, collect(CASE WHEN r IS NULL THEN null ELSE
          {from: a.name, to: b.name, type: r.type, endpoint: r.endpoint,
           evidence_kind: r.evidence_kind, source_file: r.source_file,
           source_line: r.source_line, environment_variable: r.environment_variable,
           method: r.method} END) AS dependencies
    """).single()
    data = context.to_data() if context else {}
    data["services"] = record["services"] if record else []
    data["dependencies"] = record["dependencies"] if record else []
    return GraphSnapshot.from_data(data, source="neo4j_transaction")


def detect_smells(snapshot: GraphSnapshot, thresholds: dict[str, int] | None = None) -> list[dict[str, Any]]:
    """Evaluate all ten structural/history rules against exactly one snapshot."""
    cfg = {"inbound": 3, "total_degree": 5, "coupling": 3, "growth": 3, "api_churn": 3}
    cfg.update(thresholds or {})
    data = snapshot.to_data()
    nodes = {s["name"]: s for s in data["services"]}
    fleet = {name for name, s in nodes.items() if s["node_type"] == "service"}
    edges = data["dependencies"]
    incoming, outgoing, adjacency = defaultdict(set), defaultdict(set), defaultdict(set)
    pair_counts = defaultdict(int)
    call_outgoing = defaultdict(set)
    database_incoming = defaultdict(set)
    connected = set()
    findings = []

    def add(kind, severity, services, evidence, description, confidence="high"):
        identity = {"type": kind, "services": sorted(services)}
        for key in ("cycle", "shared_target"):
            if key in evidence:
                identity[key] = evidence[key]
        fid = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        findings.append({"id": fid, "type": kind, "severity": severity, "confidence": confidence,
                         "services": sorted(services), "evidence": evidence, "description": description,
                         "detector_version": DETECTOR_VERSION})

    for edge in edges:
        src, dst = edge["from"], edge["to"]
        connected.update((src, dst))
        if is_startup(edge):
            continue
        if is_call(edge) and src in fleet and dst in fleet:
            adjacency[src].add(dst)
        if src != dst:
            incoming[dst].add(src)
            outgoing[src].add(dst)
            if is_call(edge) and src in fleet and dst in fleet:
                pair_counts[tuple(sorted((src, dst)))] += 1
                call_outgoing[src].add(dst)
            if edge["type"] in DATABASE_TYPES or is_call(edge):
                database_incoming[dst].add(src)

    steps = 0
    pairs_in_cycles = set()
    for start in sorted(fleet):
        def walk(current, path):
            nonlocal steps
            for nxt in sorted(adjacency[current]):
                steps += 1
                if steps > MAX_CYCLE_SEARCH_STEPS:
                    raise ValueError("Cycle enumeration budget exceeded; split the graph or reduce its density")
                if nxt == start:
                    cycle = path + [start]
                    if len(path) == 2:
                        pairs_in_cycles.add(tuple(sorted(path)))
                    add("Circular Dependency", "CRITICAL", path, {"cycle": cycle},
                        "Circular dependency detected: " + " → ".join(cycle) + ".")
                elif nxt > start and nxt not in path and len(path) < 8:
                    walk(nxt, path + [nxt])
        walk(start, [start])

    fanouts = {name: call_outgoing[name] & fleet for name in fleet}
    cb_threshold = circuit_breaker_threshold(len(fleet), [len(fanouts[n]) for n in sorted(fleet)])
    degrees = {name: (outgoing[name] | incoming[name]) & fleet for name in fleet}
    average_degree = sum(len(v) for v in degrees.values()) / max(1, len(fleet))
    hub_limit = hub_threshold(len(fleet))
    for name in sorted(fleet):
        inc, out = len(incoming[name]), len(outgoing[name])
        if inc >= cfg["inbound"] or inc + out >= cfg["total_degree"]:
            add("God / Bottleneck Service", "HIGH", [name], {"incoming": inc, "outgoing": out},
                f"{name} is a dependency bottleneck (incoming: {inc}, outgoing: {out}).", "medium")
        if out >= cfg["coupling"]:
            add("High Coupling", "MEDIUM", [name], {"direct_dependencies": out}, f"{name} has {out} direct dependencies.")
        if name not in connected and data["project"].get("source") != "repository":
            add("Dead / Isolated Service", "LOW", [name], {"degree": 0}, f"{name} has no graph callers or dependencies.", "medium")
        if nodes[name]["has_circuit_breaker"] is False and nodes[name]["resilient"] is False and len(fanouts[name]) >= cb_threshold:
            add("Missing Circuit Breaker", "MEDIUM", [name], {"fan_out_count": len(fanouts[name]),
                "targets": sorted(fanouts[name]), "dynamic_threshold": cb_threshold, "total_services": len(fleet)},
                f"{name} has {len(fanouts[name])} downstream services without recorded circuit-breaker evidence.", "medium")
        deg = len(degrees[name])
        if len(fleet) >= 3 and deg >= hub_limit and deg > average_degree:
            add("Hub-and-Spoke Centralization", "HIGH", [name], {"connected_count": deg, "total_services": len(fleet),
                "ratio": round(deg / (len(fleet) - 1), 3), "dynamic_threshold": hub_limit, "average_degree": round(average_degree, 3)},
                f"{name} connects to {deg}/{len(fleet)-1} peer services.")

    for name, node in sorted(nodes.items()):
        if node["node_type"] == "database" and len(database_incoming[name] & fleet) > 1:
            callers = sorted(database_incoming[name] & fleet)
            add("Shared Database", "HIGH", callers, {"shared_target": name, "sharing_services": callers},
                f"Services {', '.join(callers)} share database target '{name}'.")
    for pair, count in sorted(pair_counts.items()):
        a, b = pair
        mutual = b in adjacency[a] and a in adjacency[b]
        if count >= 3 or (mutual and pair not in pairs_in_cycles):
            add("Chatty Communication", "MEDIUM", pair, {"pair": list(pair), "edge_count": count, "bidirectional": mutual},
                f"{a} and {b} have {count} distinct dependency edges; runtime traffic is not measured.", "medium")

    histories = sorted(data["dependency_snapshots"], key=lambda s: s.get("created_at", ""), reverse=True)
    if len(histories) >= 2:
        current = set(histories[0].get("edges", []))
        previous = next((s for s in histories[1:] if set(s.get("edges", [])) != current), None)
        if previous:
            added = sorted(e for e in current - set(previous.get("edges", []))
                           if "->" in e and all(n in nodes for n in e.split("->", 1)))
            if len(added) >= cfg["growth"]:
                add("Dependency Explosion", "HIGH", {e.split("->", 1)[0] for e in added},
                    {"added_edges": added, "previous_snapshot": previous.get("created_at"), "current_snapshot": histories[0].get("created_at")},
                    f"{len(added)} dependencies were added between recorded topology snapshots.")
    api_history = defaultdict(list)
    for item in sorted(data["api_snapshots"], key=lambda s: s.get("created_at", ""), reverse=True):
        if item.get("service") in fleet and len(api_history[item["service"]]) < 2:
            api_history[item["service"]].append(item)
    for name, records in sorted(api_history.items()):
        if len(records) < 2:
            continue
        latest, previous = records
        removed = sorted(set(previous.get("endpoints", [])) - set(latest.get("endpoints", [])))
        added = sorted(set(latest.get("endpoints", [])) - set(previous.get("endpoints", [])))
        if removed or len(removed) + len(added) >= cfg["api_churn"]:
            add("API Instability", "HIGH" if removed else "MEDIUM", [name],
                {"removed_endpoints": removed, "added_endpoints": added, "previous_snapshot": previous.get("created_at"), "current_snapshot": latest.get("created_at")},
                f"{name} changed {len(removed)+len(added)} recorded API endpoint definitions.")
    return sorted(findings, key=lambda f: (f["type"], f["id"]))


def configured_thresholds() -> dict[str, int]:
    from core.config import settings
    return {"inbound": settings.SMELL_BOTTLENECK_INBOUND_THRESHOLD,
            "total_degree": settings.SMELL_BOTTLENECK_TOTAL_DEGREE_THRESHOLD,
            "coupling": settings.SMELL_HIGH_COUPLING_THRESHOLD,
            "growth": settings.SMELL_DEPENDENCY_GROWTH_THRESHOLD,
            "api_churn": settings.SMELL_API_CHURN_THRESHOLD}
