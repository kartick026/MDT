"""Regression tests for measured previews, explicit edits and immutable baselines."""
import copy
import json
import os
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from domain.architecture import GraphSnapshot, configured_thresholds, detect_smells
from services.remediation_simulator import (
    GraphEdit, RemediationSimulator, apply_snapshot_edits, breakdown_smells,
    compute_architecture_health, generate_edits_for_smells, _normalize_score,
    _compute_uncapped_score_from_smells, _calculate_simulation_metrics,
)


def make_graph(names=("a", "b", "c", "d"), pairs=(("a", "b"), ("b", "a"), ("c", "d"))):
    return GraphSnapshot.from_data({"services": [{"name": n} for n in names],
        "dependencies": [{"from": a, "to": b, "type": "http", "endpoint": ""} for a,b in pairs]})


async def preview(graph, edits, **kwargs):
    with patch("services.remediation_simulator.registry_snapshot", return_value=graph), patch("services.remediation_simulator.get_neo4j_driver", return_value=None):
        return await RemediationSimulator().simulate_fix(edits, **kwargs)


@pytest.mark.parametrize("payload", [
    {"action": "remove_edge", "from_service": "a"},
    {"action": "add_node", "from_service": " "},
    {"action": "add_node", "from_service": "a", "to_service": "b"},
    {"action": "drop_table", "from_service": "a"},
    {"action": "update_node", "from_service": "a"},
    {"action": "add_edge", "from_service": "a", "to_service": "b", "relationship_type": "DROP"},
])
def test_invalid_operations_are_rejected(payload):
    with pytest.raises(ValidationError):
        GraphEdit(**payload)


@pytest.mark.asyncio
async def test_no_edit_recomputes_baseline_and_has_zero_change():
    graph = make_graph()
    result = await preview(graph, [], baseline_smells={"circular_dependency": 999})
    assert result["before"] == compute_architecture_health(breakdown_smells(detect_smells(graph)), graph)
    assert result["before"] == result["after"]
    assert result["delta"]["score_reduction"] == 0
    assert not result["measurable_change"]
    assert result["provenance"]["baseline"] == "server_recomputed"


@pytest.mark.asyncio
async def test_removing_unrelated_edge_does_not_resolve_cycle_and_reports_new_isolation():
    graph = make_graph()
    result = await preview(graph, [GraphEdit(action="remove_edge", from_service="c", to_service="d")])
    assert result["before"]["smells"]["circular_dependency"] == result["after"]["smells"]["circular_dependency"] == 1
    assert result["delta"]["score_reduction"] < 0
    assert result["after"]["smells"]["isolated_service"] == 2
    assert len(result["removed_dependencies"]) == 1
    assert len(result["findings"]["introduced"]) == 2
    assert result["warnings"]


@pytest.mark.asyncio
async def test_adding_cycle_is_measured_as_degradation():
    graph = make_graph(("a", "b"), (("a", "b"),))
    result = await preview(graph, [GraphEdit(action="add_edge", from_service="b", to_service="a")])
    assert result["before"]["score"] == 0
    assert result["after"]["smells"]["circular_dependency"] == 1
    assert result["delta"]["score_reduction"] == -45
    assert "increases architectural risk" in result["delta"]["message"]


@pytest.mark.asyncio
async def test_removing_cycle_edge_preserves_functional_warning_and_live_input():
    graph = make_graph()
    original = graph.to_data()
    result = await preview(graph, [GraphEdit(action="remove_edge", from_service="b", to_service="a")])
    assert result["after"]["smells"]["circular_dependency"] == 0
    assert result["delta"]["score_reduction"] > 0
    assert any(f["type"] == "Circular Dependency" for f in result["findings"]["resolved"])
    assert graph.to_data() == original
    assert result["snapshot_version"] == graph.version
    assert result["preview_snapshot_version"] != graph.version


@pytest.mark.asyncio
async def test_gateway_name_does_not_grant_resilience_or_erase_findings():
    graph = make_graph(("a", "b", "c", "d"), (("a", "b"), ("a", "c"), ("a", "d")))
    result = await preview(graph, [GraphEdit(action="add_node", from_service="a_gateway")])
    assert result["after"]["smells"]["high_coupling"] == result["before"]["smells"]["high_coupling"]
    assert result["after"]["smells"]["missing_circuit_breaker"] == result["before"]["smells"]["missing_circuit_breaker"]
    assert any(f["services"] == ["a_gateway"] and f["type"] == "Dead / Isolated Service" for f in result["findings"]["introduced"])


@pytest.mark.asyncio
async def test_explicit_resilience_property_changes_only_supported_evidence():
    graph = make_graph(("a", "b", "c", "d"), (("a", "b"), ("a", "c"), ("a", "d")))
    result = await preview(graph, [GraphEdit(action="update_node", from_service="a", has_circuit_breaker=True)])
    assert result["after"]["smells"]["missing_circuit_breaker"] == 0
    assert result["after"]["smells"]["high_coupling"] == result["before"]["smells"]["high_coupling"]
    assert any("hypothetical" in warning for warning in result["warnings"])


@pytest.mark.asyncio
async def test_snapshot_version_rejects_stale_baseline():
    with pytest.raises(ValueError, match="Stale snapshot"):
        await preview(make_graph(), [], snapshot_version="old")


@pytest.mark.asyncio
async def test_unknown_service_missing_edge_and_excessive_edits_rejected():
    graph = make_graph()
    invalid = [
        [GraphEdit(action="add_edge", from_service="unknown", to_service="a")],
        [GraphEdit(action="remove_edge", from_service="a", to_service="d")],
        [GraphEdit(action="add_node", from_service=f"x{i}") for i in range(101)],
    ]
    original = graph.version
    for edits in invalid:
        with pytest.raises(ValueError):
            await preview(graph, edits)
        assert graph.version == original


def test_late_validation_error_leaves_original_snapshot_unchanged():
    graph = make_graph()
    original = graph.to_data()
    with pytest.raises(ValueError):
        apply_snapshot_edits(graph, [GraphEdit(action="add_node", from_service="new"), GraphEdit(action="remove_edge", from_service="a", to_service="d")])
    assert graph.to_data() == original


def test_ambiguous_removal_requires_an_endpoint_selector():
    data = make_graph().to_data()
    data["dependencies"].append({"from":"a", "to":"b", "type":"http", "endpoint":"/second"})
    graph = GraphSnapshot.from_data(data)
    with pytest.raises(ValueError, match="Ambiguous"):
        apply_snapshot_edits(graph, [GraphEdit(action="remove_edge", from_service="a", to_service="b")])
    after, removed = apply_snapshot_edits(graph, [GraphEdit(action="remove_edge", from_service="a", to_service="b", dependency_type="http", endpoint="/second")])
    assert removed[0]["endpoint"] == "/second"
    assert len(after.to_data()["dependencies"]) == 3


@pytest.mark.asyncio
async def test_commit_risk_is_separate_from_measured_debt():
    result = await preview(make_graph(), [], baseline_risk_score=85.125, affected_files_count=14)
    assert result["commit_risk"]["score"] == 85.125
    assert result["commit_risk"]["files_count"] == 14
    assert result["before"]["score"] != 85.125


@pytest.mark.parametrize("raw,expected", [(244,86.936),(214,85.372),(184,83.384),(154,80.769),(124,77.178),(216,85.488),(144,79.705),(75,67.164)])
def test_published_normalization_and_precision(raw, expected):
    assert _normalize_score(raw) == expected


@pytest.mark.asyncio
async def test_preview_json_preserves_three_decimal_values():
    graph = make_graph(("a", "b", "c"), (("a", "b"), ("b", "a")))
    result = json.loads(json.dumps(await preview(graph, [])))
    assert result["before"]["raw_score"] == 35
    assert result["before"]["score"] == 48.837
    assert result["before"]["normalization_constant"] == 110/3
    assert result["before"]["detector_version"]
    assert result["before"]["weights"]["circular_dependency"] == 30


def test_all_weights_and_zero():
    expected = {"circular_dependency":30,"shared_database":20,"hub_and_spoke":20,"bottleneck_service":20,
                "dependency_explosion":20,"high_coupling":15,"api_instability":15,"chatty_communication":12,
                "missing_circuit_breaker":12,"isolated_service":5}
    for kind, weight in expected.items():
        assert _compute_uncapped_score_from_smells({kind:1}) == weight
    assert _normalize_score(0) == 0
    assert _normalize_score(30) == 45
    with pytest.raises(ValueError):
        _normalize_score(float("nan"))


def test_generated_shared_database_plan_keeps_a_path_to_storage():
    graph = GraphSnapshot.from_data({"services":[{"name":"a"},{"name":"b"}],
        "dependencies":[{"from":n,"to":"store","type":"database"} for n in ("a","b")]})
    finding = next(f for f in detect_smells(graph) if f["type"] == "Shared Database")
    with patch("services.remediation_simulator.registry_snapshot", return_value=graph):
        edits = generate_edits_for_smells([finding])
    after, removed = apply_snapshot_edits(graph, edits)
    deps = after.to_data()["dependencies"]
    assert len(removed) == 2
    facade = next(e.from_service for e in edits if e.action == "add_node")
    assert any(d["from"] == facade and d["to"] == "store" for d in deps)
    assert all(any(d["from"] == name and d["to"] == facade for d in deps) for name in ("a","b"))
    assert not any(f["type"] == "Shared Database" for f in detect_smells(after))


@pytest.mark.asyncio
async def test_live_transaction_rolls_back_after_failure_in_detector():
    graph = make_graph()
    driver = MagicMock()
    tx = driver.session.return_value.__enter__.return_value.begin_transaction.return_value
    with patch("services.remediation_simulator.get_neo4j_driver", return_value=driver):
        sim = RemediationSimulator()
    with patch("services.remediation_simulator.snapshot_from_transaction", return_value=graph), patch("services.remediation_simulator.detect_smells", side_effect=RuntimeError("injected")):
        with pytest.raises(RuntimeError, match="injected"):
            await sim._simulate_live([], snapshot=graph)
    tx.rollback.assert_called_once()
    tx.commit.assert_not_called()


@pytest.mark.asyncio
async def test_transaction_mode_requires_live_connection():
    with pytest.raises(ValueError, match="live Neo4j"):
        await preview(make_graph(), [], evaluation_mode="neo4j_transaction")
