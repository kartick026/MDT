"""Tests for the What-If Remediation Simulator."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services.remediation_simulator import (
    GraphEdit,
    RemediationSimulator,
    generate_edits_for_smells,
    _compute_score_from_smells,
    _compute_uncapped_score_from_smells,
    _get_severity,
    _normalize_score,
    SATURATION_CONSTANT_K,
    _calculate_simulation_metrics,
)


class GraphEditSchemaTests(unittest.TestCase):
    """Validate the GraphEdit Pydantic model."""

    def test_remove_edge_schema(self):
        edit = GraphEdit(action="remove_edge", from_service="A", to_service="B")
        self.assertEqual(edit.action, "remove_edge")
        self.assertEqual(edit.from_service, "A")
        self.assertEqual(edit.to_service, "B")
        self.assertEqual(edit.relationship_type, "DEPENDS_ON")

    def test_add_node_schema(self):
        edit = GraphEdit(action="add_node", from_service="new_svc")
        self.assertEqual(edit.action, "add_node")
        self.assertIsNone(edit.to_service)

    def test_invalid_action_rejected(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            GraphEdit(action="drop_table", from_service="X")  # type: ignore


class ScoringSeverityTests(unittest.TestCase):
    """Verify the risk-score computation and severity mapping."""

    def test_empty_smells_score_zero(self):
        counts = {
            "circular_dependency": 0,
            "bottleneck_service": 0,
            "high_coupling": 0,
            "isolated_service": 0,
            "shared_database": 0,
            "hub_and_spoke": 0,
            "chatty_communication": 0,
            "missing_circuit_breaker": 0,
            "dependency_explosion": 0,
            "api_instability": 0,
        }
        self.assertEqual(_compute_score_from_smells(counts), 0.0)
        self.assertEqual(_compute_uncapped_score_from_smells(counts), 0.0)

    def test_scoring_weights_all_ten_smells(self):
        """Verify explicit point weighting across all 10 architectural smells."""
        self.assertEqual(_compute_uncapped_score_from_smells({"circular_dependency": 1}), 30.0)
        self.assertEqual(_compute_uncapped_score_from_smells({"shared_database": 1}), 20.0)
        self.assertEqual(_compute_uncapped_score_from_smells({"hub_and_spoke": 1}), 20.0)
        self.assertEqual(_compute_uncapped_score_from_smells({"bottleneck_service": 1}), 20.0)
        self.assertEqual(_compute_uncapped_score_from_smells({"dependency_explosion": 1}), 20.0)
        self.assertEqual(_compute_uncapped_score_from_smells({"high_coupling": 1}), 15.0)
        self.assertEqual(_compute_uncapped_score_from_smells({"api_instability": 1}), 15.0)
        self.assertEqual(_compute_uncapped_score_from_smells({"chatty_communication": 1}), 12.0)
        self.assertEqual(_compute_uncapped_score_from_smells({"missing_circuit_breaker": 1}), 12.0)
        self.assertEqual(_compute_uncapped_score_from_smells({"isolated_service": 1}), 5.0)

    def test_single_cycle_scores_anchor_point(self):
        counts = {
            "circular_dependency": 1,
        }
        self.assertEqual(_compute_score_from_smells(counts), 45.0)

    def test_score_caps_asymptotically_below_100(self):
        counts = {
            "circular_dependency": 5,
            "bottleneck_service": 3,
            "high_coupling": 2,
            "isolated_service": 10,
        }
        self.assertEqual(_compute_score_from_smells(counts), 88.8)
        self.assertLess(_compute_score_from_smells(counts), 100.0)
        self.assertGreater(_compute_uncapped_score_from_smells(counts), 100.0)

    def test_severity_mapping(self):
        self.assertEqual(_get_severity(80), "CRITICAL")
        self.assertEqual(_get_severity(60), "HIGH")
        self.assertEqual(_get_severity(30), "MEDIUM")
        self.assertEqual(_get_severity(10), "LOW")


class GenerateEditsTests(unittest.TestCase):
    """Test deterministic edit generation from smell findings."""

    def test_cycle_generates_remove_edge(self):
        smells = [{
            "type": "Circular Dependency",
            "services": ["A", "B"],
            "evidence": {"cycle": ["A", "B", "A"]},
        }]
        edits = generate_edits_for_smells(smells)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].action, "remove_edge")
        self.assertEqual(edits[0].from_service, "B")
        self.assertEqual(edits[0].to_service, "A")

    def test_bottleneck_generates_facade(self):
        smells = [{
            "type": "God / Bottleneck Service",
            "services": ["payment_service"],
            "evidence": {"incoming": 5, "outgoing": 2},
        }]
        edits = generate_edits_for_smells(smells)
        self.assertEqual(len(edits), 2)
        self.assertEqual(edits[0].action, "add_node")
        self.assertEqual(edits[0].from_service, "payment_service_facade")
        self.assertEqual(edits[1].action, "add_edge")
        self.assertEqual(edits[1].to_service, "payment_service")

    def test_coupling_generates_gateway(self):
        smells = [{
            "type": "High Coupling",
            "services": ["order_service"],
            "evidence": {"direct_dependencies": 6},
        }]
        edits = generate_edits_for_smells(smells)
        self.assertEqual(len(edits), 2)
        self.assertEqual(edits[0].action, "add_node")
        self.assertIsNotNone(edits[0].from_service)
        assert edits[0].from_service is not None
        self.assertIn("gateway", edits[0].from_service)

    def test_isolated_generates_edge_to_dynamic_target(self):
        smells = [{
            "type": "Dead / Isolated Service",
            "services": ["orphan_service"],
            "evidence": {"degree": 0},
        }]
        edits = generate_edits_for_smells(smells)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].action, "add_edge")
        self.assertEqual(edits[0].to_service, "orphan_service")
        # Should dynamically pick an existing service from registry or api-gateway
        self.assertIsNotNone(edits[0].from_service)
        self.assertNotEqual(edits[0].from_service, "orphan_service")

    def test_empty_smells_yields_no_edits(self):
        self.assertEqual(generate_edits_for_smells([]), [])

    def test_shared_database_generates_facade_and_reroute(self):
        smells = [{
            "type": "Shared Database",
            "services": ["orders", "payments"],
            "evidence": {"shared_target": "postgres-db"},
        }]
        edits = generate_edits_for_smells(smells)
        self.assertEqual(len(edits), 3)
        self.assertEqual(edits[0].action, "add_node")
        self.assertEqual(edits[0].from_service, "orders_data_facade")
        self.assertEqual(edits[1].action, "add_edge")
        self.assertEqual(edits[1].from_service, "payments")
        self.assertEqual(edits[1].to_service, "orders_data_facade")
        self.assertEqual(edits[2].action, "remove_edge")
        self.assertEqual(edits[2].from_service, "payments")
        self.assertEqual(edits[2].to_service, "postgres-db")

    def test_chatty_communication_generates_broker(self):
        smells = [{
            "type": "Chatty Communication",
            "services": ["orders", "users"],
            "evidence": {"pair": ["orders", "users"]},
        }]
        edits = generate_edits_for_smells(smells)
        self.assertEqual(len(edits), 4)
        self.assertEqual(edits[0].action, "add_node")
        self.assertEqual(edits[0].from_service, "event_broker")

    def test_circuit_breaker_generates_gateway(self):
        smells = [{
            "type": "Missing Circuit Breaker",
            "services": ["api-client"],
            "evidence": {"fan_out_count": 4},
        }]
        edits = generate_edits_for_smells(smells)
        self.assertEqual(len(edits), 2)
        self.assertEqual(edits[0].action, "add_node")
        self.assertEqual(edits[0].from_service, "api-client_gateway")


class SimulatorMockModeTests(unittest.IsolatedAsyncioTestCase):
    """Test the simulator in mock/fallback mode (no live Neo4j)."""

    @patch("services.remediation_simulator.get_neo4j_driver")
    async def test_mock_mode_returns_valid_structure(self, mock_get_driver):
        from core.database import MockNeo4jDriver
        mock_get_driver.return_value = MockNeo4jDriver()

        sim = RemediationSimulator()
        edits = [GraphEdit(action="remove_edge", from_service="A", to_service="B")]
        result = await sim.simulate_fix(edits)

        self.assertTrue(result["sandbox"])
        self.assertIn("before", result)
        self.assertIn("after", result)
        self.assertIn("delta", result)
        self.assertIn("score", result["before"])
        self.assertIn("severity", result["before"])
        self.assertIn("smells", result["before"])
        self.assertIn("score_reduction", result["delta"])
        self.assertIn("smells_resolved", result["delta"])
        self.assertEqual(result["metric"], "Architectural Smell Risk")

    @patch("services.smell_detector.SmellDetector.detect_all_smells", new_callable=AsyncMock, return_value=[])
    @patch("services.remediation_simulator.get_neo4j_driver")
    async def test_mock_mode_with_no_smells(self, mock_get_driver, mock_detect_smells):
        from core.database import MockNeo4jDriver
        mock_get_driver.return_value = MockNeo4jDriver()

        sim = RemediationSimulator()
        edits = [GraphEdit(action="add_node", from_service="new_service")]
        result = await sim.simulate_fix(edits)

        # Honest reporting when no tracked smells change
        self.assertEqual(result["before"]["score"], 0.0)
        self.assertEqual(result["after"]["score"], 0.0)
        self.assertEqual(result["delta"]["score_reduction"], 0.0)
        self.assertEqual(result["delta"]["smells_resolved"], 0)
        self.assertFalse(result["delta"]["measurable_change"])
        self.assertFalse(result["measurable_change"])

    @patch("services.remediation_simulator.get_neo4j_driver")
    async def test_null_driver_uses_mock_mode(self, mock_get_driver):
        mock_get_driver.return_value = None

        sim = RemediationSimulator()
        edits = [GraphEdit(action="remove_edge", from_service="X", to_service="Y")]
        result = await sim.simulate_fix(edits)

        self.assertTrue(result["sandbox"])
        self.assertIn("before", result)

    @patch("services.smell_detector.SmellDetector.detect_all_smells", new_callable=AsyncMock)
    @patch("services.remediation_simulator.get_neo4j_driver")
    async def test_baseline_risk_score_with_resilience_facade(self, mock_get_driver, mock_detect_smells):
        from core.database import MockNeo4jDriver
        mock_get_driver.return_value = MockNeo4jDriver()
        mock_detect_smells.return_value = [
            {"type": "Circular Dependency", "services": ["order-service", "user-service"]}
        ]

        sim = RemediationSimulator()
        edits = [
            GraphEdit(action="remove_edge", from_service="order-service", to_service="user-service"),
            GraphEdit(action="add_node", from_service="order-service_facade"),
            GraphEdit(action="add_edge", from_service="order-service_facade", to_service="order-service"),
            GraphEdit(action="add_edge", from_service="order-service_facade", to_service="user-service"),
        ]
        result = await sim.simulate_fix(edits, baseline_risk_score=85.0, affected_files_count=14)

        # Architectural smell risk is independent of git diff score; normalized raw=30 -> 45.0
        self.assertEqual(result["before"]["score"], 45.0)
        self.assertEqual(result["before"]["severity"], "MEDIUM")
        self.assertEqual(result["after"]["score"], 0.0)
        self.assertEqual(result["after"]["severity"], "LOW")
        self.assertEqual(result["delta"]["score_reduction"], 45.0)
        self.assertTrue(result["delta"]["measurable_change"])
        self.assertEqual(result["metric"], "Architectural Smell Risk")

        # Commit risk is preserved separately
        self.assertIsNotNone(result["commit_risk"])
        assert result["commit_risk"] is not None
        self.assertEqual(result["commit_risk"]["score"], 85.0)
        self.assertEqual(result["commit_risk"]["severity"], "CRITICAL")
        self.assertEqual(result["commit_risk"]["files_count"], 14)
        self.assertIn("14 source files", result["commit_risk"]["message"])

    @patch("services.remediation_simulator.get_neo4j_driver")
    async def test_baseline_risk_score_with_no_resilience_edits(self, mock_get_driver):
        from core.database import MockNeo4jDriver
        mock_get_driver.return_value = MockNeo4jDriver()

        sim = RemediationSimulator()
        edits = [GraphEdit(action="add_node", from_service="unrelated_node")]
        result = await sim.simulate_fix(edits, baseline_risk_score=85.0)

        # Architectural smell score is unchanged when edits do not resolve smells
        self.assertEqual(result["before"]["score"], result["after"]["score"])
        self.assertEqual(result["delta"]["score_reduction"], 0.0)
        self.assertFalse(result["delta"]["measurable_change"])

        # Commit risk remains reported
        self.assertIsNotNone(result["commit_risk"])
        assert result["commit_risk"] is not None
        self.assertEqual(result["commit_risk"]["score"], 85.0)
        self.assertEqual(result["commit_risk"]["severity"], "CRITICAL")

    @patch("services.smell_detector.SmellDetector.detect_all_smells", new_callable=AsyncMock)
    @patch("services.remediation_simulator.get_neo4j_driver")
    async def test_shared_database_simulation_score_reduction(self, mock_get_driver, mock_detect_smells):
        """Resolving a Shared Database finding must reduce architectural smell score and show measurable change."""
        from core.database import MockNeo4jDriver
        mock_get_driver.return_value = MockNeo4jDriver()
        mock_detect_smells.return_value = [{
            "type": "Shared Database",
            "services": ["order-service", "payment-service"],
            "evidence": {"shared_target": "postgres-db", "sharing_services": ["order-service", "payment-service"]},
        }]

        sim = RemediationSimulator()
        edits = [
            GraphEdit(action="add_node", from_service="order-service_facade"),
            GraphEdit(action="add_edge", from_service="payment-service", to_service="order-service_facade"),
            GraphEdit(action="remove_edge", from_service="payment-service", to_service="postgres-db"),
        ]
        result = await sim.simulate_fix(edits)

        # Before: 1 Shared Database (weight 20) -> normalized score = 35.3
        self.assertEqual(result["before"]["score"], 35.3)
        self.assertEqual(result["before"]["smells"]["shared_database"], 1)

        # After: 0 Shared Database -> score = 0.0
        self.assertEqual(result["after"]["score"], 0.0)
        self.assertEqual(result["after"]["smells"]["shared_database"], 0)

        # Score reduction & measurable change verified
        self.assertEqual(result["delta"]["score_reduction"], 35.3)
        self.assertEqual(result["delta"]["smells_resolved"], 1)
        self.assertTrue(result["delta"]["measurable_change"])
        self.assertIn("shared database resolved", result["delta"]["message"])
        self.assertLess(result["after"]["score"], result["before"]["score"])

    @patch("services.smell_detector.SmellDetector.detect_all_smells", new_callable=AsyncMock)
    @patch("services.remediation_simulator.get_neo4j_driver")
    async def test_gateway_simulation_resolves_high_coupling_without_false_cycles(self, mock_get_driver, mock_detect_smells):
        """Simulating a gateway facade reduces coupling and score without introducing cycles."""
        from core.database import MockNeo4jDriver
        mock_get_driver.return_value = MockNeo4jDriver()
        mock_detect_smells.return_value = [
            {"type": "High Coupling", "services": ["order-service"]},
            {"type": "God / Bottleneck Service", "services": ["order-service"]},
        ]

        sim = RemediationSimulator()
        edits = [
            GraphEdit(action="add_node", from_service="order-service_gateway"),
            GraphEdit(action="add_edge", from_service="order-service_gateway", to_service="order-service"),
        ]
        result = await sim.simulate_fix(edits)

        self.assertEqual(result["before"]["smells"]["high_coupling"], 1)
        self.assertEqual(result["after"]["smells"]["high_coupling"], 0)
        self.assertEqual(result["after"]["smells"]["circular_dependency"], 0)
        self.assertEqual(result["after"]["smells"]["missing_circuit_breaker"], 0)
        self.assertTrue(result["delta"]["measurable_change"])
        self.assertGreater(result["delta"]["score_reduction"], 0)

    @patch("services.smell_detector.SmellDetector.detect_all_smells", new_callable=AsyncMock)
    @patch("services.remediation_simulator.get_neo4j_driver")
    async def test_resilience_facade_simulation_resolves_missing_circuit_breaker(self, mock_get_driver, mock_detect_smells):
        """Simulating a resilience facade resolves missing circuit breaker and bottleneck."""
        from core.database import MockNeo4jDriver
        mock_get_driver.return_value = MockNeo4jDriver()
        mock_detect_smells.return_value = [
            {"type": "Missing Circuit Breaker", "services": ["order-service"]},
            {"type": "God / Bottleneck Service", "services": ["order-service"]},
        ]

        sim = RemediationSimulator()
        edits = [
            GraphEdit(action="add_node", from_service="order-service_facade"),
            GraphEdit(action="add_edge", from_service="order-service_facade", to_service="order-service"),
        ]
        result = await sim.simulate_fix(edits)

        self.assertEqual(result["before"]["smells"]["missing_circuit_breaker"], 1)
        self.assertEqual(result["after"]["smells"]["missing_circuit_breaker"], 0)
        self.assertEqual(result["after"]["smells"]["circular_dependency"], 0)
        self.assertTrue(result["delta"]["measurable_change"])
        self.assertGreater(result["delta"]["score_reduction"], 0)


class SaturatingScoreRegressionTests(unittest.TestCase):
    """Regression test for saturating score calculation.
    
    Verifies that _normalize_score properly differentiates after-states
    when raw cumulative smell debt is large, eliminating score ties.
    """

    def test_normalize_score_anchor_point(self):
        """Single circular dependency (raw=30) anchors to MEDIUM score (45.0)."""
        self.assertEqual(_normalize_score(0.0), 0.0)
        self.assertEqual(_normalize_score(30.0), 45.0)

    def test_screenshot_scenario_no_ties(self):
        """Actual screenshot scenario: raw_before=216, after-states 144 and 75.
        
        Asserts that two different after-states produce two strictly distinct scores
        and distinct point reductions rather than tying.
        """
        raw_before = 216.0
        raw_after_1 = 144.0
        raw_after_2 = 75.0

        score_before = _normalize_score(raw_before)
        score_after_1 = _normalize_score(raw_after_1)
        score_after_2 = _normalize_score(raw_after_2)

        self.assertEqual(score_before, 85.5)
        self.assertEqual(score_after_1, 79.7)
        self.assertEqual(score_after_2, 67.2)
        # Crucial assertion: the two after states must NOT tie!
        self.assertNotEqual(score_after_1, score_after_2)
        self.assertGreater(score_after_1, score_after_2)

        # Verify via _calculate_simulation_metrics end-to-end
        # High before-state (raw=215: 7 cycles * 30 + 1 isolated * 5)
        smells_high = {"circular_dependency": 7, "isolated_service": 1}
        # Two distinct reduced after-states
        smells_mid = {"circular_dependency": 4, "bottleneck_service": 1}  # raw=140: 4*30 + 1*20
        smells_low = {"circular_dependency": 2, "high_coupling": 1}       # raw=75: 2*30 + 1*15

        # Directly verify that metrics calculation uses _normalize_score:
        b1, a1, red1, change1, msg1 = _calculate_simulation_metrics(smells_high, smells_mid, [])
        b2, a2, red2, change2, msg2 = _calculate_simulation_metrics(smells_high, smells_low, [])

        self.assertEqual(b1, b2)  # baseline before score is identical
        self.assertEqual(b1, _normalize_score(215.0))
        self.assertEqual(a1, _normalize_score(140.0))
        self.assertEqual(a2, _normalize_score(75.0))
        self.assertNotEqual(a1, a2, "Two different after-states must produce two distinct scores, not ties!")
        self.assertNotEqual(red1, red2, "Two different after-states must produce distinct point reductions!")
        self.assertTrue(change1)
        self.assertTrue(change2)


if __name__ == "__main__":
    unittest.main()
