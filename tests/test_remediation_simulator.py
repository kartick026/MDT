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
            GraphEdit(action="drop_table", from_service="X")


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
        self.assertIn("gateway", edits[0].from_service)

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

        self.assertIn("before", result)
        self.assertIn("after", result)
        self.assertIn("delta", result)
        self.assertTrue(result["sandbox"])
        self.assertIn("score", result["before"])
        self.assertIn("severity", result["before"])
        self.assertIn("smells", result["before"])
        self.assertIn("score_reduction", result["delta"])
        self.assertIn("smells_resolved", result["delta"])

    @patch("services.remediation_simulator.get_neo4j_driver")
    async def test_mock_mode_with_no_smells(self, mock_get_driver):
        from core.database import MockNeo4jDriver
        mock_get_driver.return_value = MockNeo4jDriver()

        sim = RemediationSimulator()
        edits = [GraphEdit(action="add_node", from_service="new_service")]
        result = await sim.simulate_fix(edits)

        self.assertEqual(result["before"]["score"], 40.0)
        self.assertEqual(result["after"]["score"], 15.0)
        self.assertEqual(result["delta"]["score_reduction"], 25.0)

    @patch("services.remediation_simulator.get_neo4j_driver")
    async def test_null_driver_uses_mock_mode(self, mock_get_driver):
        mock_get_driver.return_value = None

        sim = RemediationSimulator()
        edits = [GraphEdit(action="remove_edge", from_service="X", to_service="Y")]
        result = await sim.simulate_fix(edits)

        self.assertTrue(result["sandbox"])
        self.assertIn("before", result)


if __name__ == "__main__":
    unittest.main()
