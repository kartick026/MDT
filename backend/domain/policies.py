"""Explicit dependency constraints evaluated only against captured topology."""
import hashlib
import json


def policy_version(rules):
    return hashlib.sha256(json.dumps(rules, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]


def evaluate_policies(snapshot, rules):
    nodes = {service["name"] for service in snapshot.get("services", [])}
    edges = {(edge.get("from"), edge.get("to")) for edge in snapshot.get("dependencies", [])}
    evaluations = []
    for rule in rules:
        observed = (rule["source"], rule["target"]) in edges
        status = ("unresolved" if not {rule["source"], rule["target"]} <= nodes else
                  "satisfied" if observed == (rule["kind"] == "require") else "violated")
        evaluations.append({**rule, "status": status, "edge_observed": observed})
    return {"version": policy_version(rules), "rules": evaluations,
            "violations": sum(rule["status"] == "violated" for rule in evaluations),
            "unresolved": sum(rule["status"] == "unresolved" for rule in evaluations),
            "scope": "captured_topology", "score_effect": "none",
            "limitation": "Dependency rules check recorded source topology; they do not verify runtime behavior or unimported code changes."}
