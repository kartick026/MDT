"""Compare captured architecture evidence without implying unmeasured runtime drift."""
from __future__ import annotations

from collections import defaultdict
import re

from domain.architecture import GraphSnapshot, configured_thresholds, detect_smells
from services.remediation_simulator import breakdown_smells, compute_architecture_health


def snapshot_metadata(record: dict) -> dict:
    context = record.get("snapshot", {}).get("project", {})
    return {"snapshot_version": record["snapshot_version"], "captured_at": record.get("captured_at"),
            "source_analysis_id": record.get("source_analysis_id"),
            "revision": record.get("revision", context.get("revision")),
            "source": record.get("source", context.get("source", "unknown"))}


def _contracts(data: dict) -> dict:
    grouped = defaultdict(list)
    for service in data["services"]:
        for endpoint in service.get("api_endpoints", []):
            grouped[(service["name"], endpoint["method"], endpoint["path"])].append(endpoint)
    contracts = {}
    for key, variants in sorted(grouped.items()):
        service, method, path = key
        contracts[key] = ({"service": service, **variants[0]} if len(variants) == 1 else
                          {"service": service, "method": method, "path": path, "variants": variants})
    return contracts


def compare_snapshots(base: dict, target: dict) -> dict:
    before = GraphSnapshot.from_data(base["snapshot"])
    after = GraphSnapshot.from_data(target["snapshot"])
    left, right = before.to_data(), after.to_data()
    left_nodes = {node["name"]: {k: v for k, v in node.items() if k != "api_endpoints"} for node in left["services"]}
    right_nodes = {node["name"]: {k: v for k, v in node.items() if k != "api_endpoints"} for node in right["services"]}
    edge_key = lambda edge: (edge["from"], edge["to"], edge["type"], edge["endpoint"])
    left_edges, right_edges = ({edge_key(edge): edge for edge in data["dependencies"]} for data in (left, right))
    left_contracts, right_contracts = _contracts(left), _contracts(right)
    left_findings = {finding["id"]: finding for finding in detect_smells(before, configured_thresholds())}
    right_findings = {finding["id"]: finding for finding in detect_smells(after, configured_thresholds())}
    left_health = compute_architecture_health(breakdown_smells(list(left_findings.values())), before)
    right_health = compute_architecture_health(breakdown_smells(list(right_findings.values())), after)
    delta = round(right_health["score"] - left_health["score"], 3)
    raw_delta = right_health["raw_score"] - left_health["raw_score"]
    base_meta, target_meta = snapshot_metadata(base), snapshot_metadata(target)
    same_snapshot = base["snapshot_version"] == target["snapshot_version"]
    revisions = (base_meta["revision"], target_meta["revision"])
    revision_comparison = (not same_snapshot and all(re.fullmatch(r"[a-fA-F0-9]{40}", str(value or "")) for value in revisions)
                           and revisions[0] != revisions[1] and base_meta["source"] == target_meta["source"] == "repository")
    warnings = ["Static captured declarations only; runtime traffic and complete API compatibility are not measured."]
    if same_snapshot:
        warnings.append("Both selections use the same captured topology. Commit or patch analysis reuses topology; import a revision to capture a new architecture.")
    elif not revision_comparison:
        warnings.append("These captures do not establish a comparison between two distinct resolved repository revisions.")
    if any(meta["source"] == "illustrative_demo" for meta in (base_meta, target_meta)):
        warnings.append("Illustrative demo history is fixture data, not observed repository evolution.")
    if any(key[1] == "UNKNOWN" for key in left_contracts.keys() | right_contracts.keys()):
        warnings.append("Some legacy endpoints have no captured HTTP method; those methods are shown as UNKNOWN.")
    for label, record in (("base", base), ("target", target)):
        coverage = record.get("coverage", record["snapshot"].get("coverage", {}))
        warnings.extend(f"{label}: {warning}" for warning in coverage.get("warnings", []))

    return {
        "base_version": base["snapshot_version"], "target_version": target["snapshot_version"],
        "base": base_meta, "target": target_meta,
        "services": {
            "added": [right_nodes[key] for key in sorted(right_nodes.keys() - left_nodes.keys())],
            "removed": [left_nodes[key] for key in sorted(left_nodes.keys() - right_nodes.keys())],
            "modified": [{"name": key, "before": left_nodes[key], "after": right_nodes[key]}
                         for key in sorted(left_nodes.keys() & right_nodes.keys()) if left_nodes[key] != right_nodes[key]],
        },
        "dependencies": {
            "added": [right_edges[key] for key in sorted(right_edges.keys() - left_edges.keys())],
            "removed": [left_edges[key] for key in sorted(left_edges.keys() - right_edges.keys())],
        },
        "contracts": {
            "added": [right_contracts[key] for key in sorted(right_contracts.keys() - left_contracts.keys())],
            "removed": [left_contracts[key] for key in sorted(left_contracts.keys() - right_contracts.keys())],
            "modified": [{"service": key[0], "method": key[1], "path": key[2], "before": left_contracts[key], "after": right_contracts[key]}
                         for key in sorted(left_contracts.keys() & right_contracts.keys()) if left_contracts[key] != right_contracts[key]],
        },
        "scores": {"base": left_health["score"], "target": right_health["score"], "delta": delta,
                   "direction": "improved" if raw_delta < 0 else "worsened" if raw_delta > 0 else "unchanged"},
        "findings": {"introduced": [right_findings[key] for key in sorted(right_findings.keys() - left_findings.keys())],
                     "resolved": [left_findings[key] for key in sorted(left_findings.keys() - right_findings.keys())],
                     "unchanged_count": len(left_findings.keys() & right_findings.keys())},
        "evidence": {"mode": "captured_snapshot_comparison", "same_snapshot": same_snapshot,
                     "revision_comparison": bool(revision_comparison), "semantic_used": False, "warnings": warnings},
    }
