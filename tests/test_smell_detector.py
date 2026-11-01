"""Canonical detectors run on actual graphs, independent of database mocks."""
import copy
from unittest.mock import patch
import pytest
from domain.architecture import GraphSnapshot, detect_smells, circuit_breaker_threshold, hub_threshold
from services.smell_detector import SmellDetector
from services.remediation_simulator import breakdown_smells


def snapshot(names, pairs=(), **extra):
    return GraphSnapshot.from_data({
        "services": [{"name": name} if isinstance(name, str) else name for name in names],
        "dependencies": [{"from": a, "to": b, "type": "http"} for a, b in pairs],
        **extra,
    })


def of_type(graph, kind):
    return [f for f in detect_smells(graph) if f["type"] == kind]


def test_simple_cycles_are_canonical_and_self_loops_are_evidence():
    graph = snapshot(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a"), ("b", "b")])
    cycles = of_type(graph, "Circular Dependency")
    assert {tuple(f["evidence"]["cycle"]) for f in cycles} == {("a", "b", "c", "a"), ("b", "b")}
    assert len({f["id"] for f in cycles}) == 2


def test_parallel_endpoints_do_not_duplicate_a_cycle():
    graph = snapshot(["a", "b"], dependencies=[
        {"from": "a", "to": "b", "endpoint": "/one"},
        {"from": "a", "to": "b", "endpoint": "/two"},
        {"from": "b", "to": "a"},
    ])
    assert len(of_type(graph, "Circular Dependency")) == 1
    assert len(of_type(graph, "Chatty Communication")) == 1


def test_two_node_cycle_is_not_double_counted_as_chatter():
    graph = snapshot(["a", "b"], [("a", "b"), ("b", "a")])
    assert len(of_type(graph, "Circular Dependency")) == 1
    assert of_type(graph, "Chatty Communication") == []


def test_bottleneck_counts_distinct_callers():
    graph = snapshot(["hub", "a", "b", "c"], [("a", "hub"), ("b", "hub"), ("c", "hub")])
    finding = of_type(graph, "God / Bottleneck Service")[0]
    assert finding["services"] == ["hub"]
    assert finding["evidence"] == {"incoming": 3, "outgoing": 0}


def test_parallel_endpoint_edges_do_not_inflate_coupling():
    graph = snapshot(["a", "b"], dependencies=[{"from": "a", "to": "b", "endpoint": f"/{i}"} for i in range(7)])
    assert not of_type(graph, "High Coupling")


def test_high_coupling_is_measured_from_distinct_targets():
    graph = snapshot(["a", "b", "c", "d"], [("a", "b"), ("a", "c"), ("a", "d")])
    assert of_type(graph, "High Coupling")[0]["evidence"]["direct_dependencies"] == 3


def test_named_facades_gateways_and_brokers_are_not_implicitly_exempt():
    graph = snapshot(["order_facade", "payment_gateway", "event_broker", {"name": "actual-broker", "node_type": "broker"}])
    names = {f["services"][0] for f in of_type(graph, "Dead / Isolated Service")}
    assert names == {"order_facade", "payment_gateway", "event_broker"}


def test_unknown_dependency_target_is_external_not_an_extra_runnable_service():
    graph = snapshot(["a"], [("a", "unresolved-target")])
    nodes = {n["name"]: n for n in graph.to_data()["services"]}
    assert nodes["unresolved-target"]["node_type"] == "external"
    assert not of_type(graph, "Missing Circuit Breaker")


def test_shared_database_uses_explicit_resource_type_not_name():
    graph = snapshot(["orders", "payments", {"name": "storage", "node_type": "database"}], [("orders", "storage"), ("payments", "storage")])
    assert of_type(graph, "Shared Database")[0]["evidence"]["shared_target"] == "storage"
    ordinary = snapshot(["orders", "payments", "db-named-service"], [("orders", "db-named-service"), ("payments", "db-named-service")])
    assert not of_type(ordinary, "Shared Database")


def test_database_typed_edges_upgrade_legacy_resource_metadata():
    graph = snapshot(["a", "b"], dependencies=[{"from": n, "to": "storage", "type": "postgresql"} for n in ("a", "b")])
    assert len(of_type(graph, "Shared Database")) == 1


def test_circuit_breaker_evidence_must_be_explicit():
    base = snapshot(["hub_gateway", "a", "b", "c"], [("hub_gateway", n) for n in ("a", "b", "c")])
    assert of_type(base, "Missing Circuit Breaker")
    data = base.to_data()
    next(n for n in data["services"] if n["name"] == "hub_gateway")["has_circuit_breaker"] = True
    assert not of_type(GraphSnapshot.from_data(data), "Missing Circuit Breaker")


def test_hub_threshold_rejects_symmetric_mesh():
    names = ["a", "b", "c", "d"]
    graph = snapshot(names, [(a, b) for a in names for b in names if a < b])
    assert not of_type(graph, "Hub-and-Spoke Centralization")


def test_hub_threshold_detects_star():
    graph = snapshot(["hub", "a", "b", "c", "d"], [("hub", n) for n in ("a", "b", "c", "d")])
    assert of_type(graph, "Hub-and-Spoke Centralization")[0]["services"] == ["hub"]


def test_historical_growth_requires_two_distinct_actual_snapshots():
    graph = snapshot(["a", "b", "c", "d", "e"], dependency_snapshots=[
        {"edges": ["a->b"], "created_at": "2026-01-01"},
        {"edges": ["a->b", "a->c", "a->d", "a->e"], "created_at": "2026-01-02"},
    ])
    assert of_type(graph, "Dependency Explosion")[0]["evidence"]["added_edges"] == ["a->c", "a->d", "a->e"]
    data = graph.to_data()
    data["dependency_snapshots"] = data["dependency_snapshots"][:1] * 2
    assert not of_type(GraphSnapshot.from_data(data), "Dependency Explosion")


def test_api_history_detects_removed_endpoint_but_ignores_unchanged():
    data = {"api_snapshots": [
        {"service": "orders", "endpoints": ["GET /orders", "POST /orders"], "created_at": "2026-01-01"},
        {"service": "orders", "endpoints": ["GET /orders"], "created_at": "2026-01-02"},
    ]}
    graph = snapshot(["orders"], **data)
    assert of_type(graph, "API Instability")[0]["evidence"]["removed_endpoints"] == ["POST /orders"]
    data["api_snapshots"][1]["endpoints"].append("POST /orders")
    assert not of_type(snapshot(["orders"], **data), "API Instability")


def test_foreign_history_does_not_enter_a_project():
    graph = snapshot(["mine"], api_snapshots=[
        {"service": "foreign", "endpoints": ["GET /x"], "created_at": "1"},
        {"service": "foreign", "endpoints": [], "created_at": "2"},
    ])
    assert not of_type(graph, "API Instability")


def test_renaming_preserves_all_counts_and_scores():
    graph = snapshot(["hub", "a", "b", "c"], [("hub", "a"), ("hub", "b"), ("hub", "c"), ("a", "hub")])
    data = graph.to_data()
    rename = {"hub": "event_broker", "a": "a_facade", "b": "b_gateway", "c": "postgresdb"}
    for node in data["services"]:
        node["name"] = rename[node["name"]]
    for edge in data["dependencies"]:
        edge["from"], edge["to"] = rename[edge["from"]], rename[edge["to"]]
    assert breakdown_smells(detect_smells(graph)) == breakdown_smells(detect_smells(GraphSnapshot.from_data(data)))


@pytest.mark.parametrize("count,expected", [(2,2), (3,2), (5,3), (9,3), (10,4), (25,5)])
def test_circuit_breaker_threshold(count, expected):
    assert circuit_breaker_threshold(count) == expected


def test_distribution_modulates_circuit_breaker_threshold():
    assert circuit_breaker_threshold(16, [2] + [0] * 15) == 2


@pytest.mark.parametrize("count,expected", [(1,0), (2,0), (3,2), (4,2), (5,3), (10,7), (200,170)])
def test_hub_threshold(count, expected):
    assert hub_threshold(count) == expected


@pytest.mark.asyncio
async def test_detector_adapter_uses_same_snapshot_with_no_graph_mutations():
    graph = snapshot(["a", "b"], [("a", "b"), ("b", "a")])
    with patch("services.smell_detector.get_neo4j_driver", return_value=None):
        detector = SmellDetector()
    with patch("services.smell_detector._run_query") as query:
        assert await detector.detect_all_smells(graph) == detect_smells(graph)
        query.assert_not_called()


def test_snapshot_is_owned_and_mapping_changes_invalidate_its_version():
    graph = snapshot(["a"], file_mappings={"services/a": "a"})
    data = graph.to_data()
    data["services"].clear()
    assert len(graph.to_data()["services"]) == 1
    data = graph.to_data()
    data["file_mappings"] = {"services/other": "a"}
    assert GraphSnapshot.from_data(data).version != graph.version
