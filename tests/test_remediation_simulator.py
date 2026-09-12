"""Tests for the What-If Remediation Simulator."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services.remediation_simulator import (
    GraphEdit,
    RemediationSimulator,
    generate_edits_for_smells,
    _compute_score_from_smells,
    _get_severity,
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
        }
        self.assertEqual(_compute_score_from_smells(counts), 0.0)

    def test_single_cycle_scores_30(self):
        counts = {
            "circular_dependency": 1,
            "bottleneck_service": 0,
            "high_coupling": 0,
            "isolated_service": 0,
        }
        self.assertEqual(_compute_score_from_smells(counts), 30.0)

    def test_score_caps_at_100(self):
        counts = {
            "circular_dependency": 5,
            "bottleneck_service": 3,
            "high_coupling": 2,
            "isolated_service": 10,
        }
        self.assertEqual(_compute_score_from_smells(counts), 100.0)

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
        result = await sim.simulate_fix(edits, baseline_risk_score=85.0)

        self.assertEqual(result["before"]["score"], 85.0)
        self.assertEqual(result["before"]["severity"], "CRITICAL")
        self.assertEqual(result["after"]["score"], 60.0)
        self.assertEqual(result["after"]["severity"], "HIGH")
        self.assertEqual(result["delta"]["score_reduction"], 25.0)
        self.assertTrue(result["delta"]["measurable_change"])
        self.assertEqual(result["metric"], "Architectural Smell Risk")

    @patch("services.remediation_simulator.get_neo4j_driver")
    async def test_baseline_risk_score_with_no_resilience_edits(self, mock_get_driver):
        from core.database import MockNeo4jDriver
        mock_get_driver.return_value = MockNeo4jDriver()

        sim = RemediationSimulator()
        edits = [GraphEdit(action="add_node", from_service="unrelated_node")]
        result = await sim.simulate_fix(edits, baseline_risk_score=85.0)

        self.assertEqual(result["before"]["score"], 85.0)
        self.assertEqual(result["after"]["score"], 85.0)
        self.assertEqual(result["delta"]["score_reduction"], 0.0)
        self.assertFalse(result["delta"]["measurable_change"])


if __name__ == "__main__":
    unittest.main()
