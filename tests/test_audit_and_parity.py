"""
Regression tests for:
1. What-If Preview after-score calculation consistency (raw_before > 100 vs <= 100).
2. Chatty Communication / Circular Dependency exclude_pairs wiring.
3. SmellDetector in-memory graph fallbacks under MockNeo4jDriver (all structural smells).
4. Degree-based centrality for core service detection.
5. Dynamic remediation target fallback (no hardcoded 'api-gateway').
6. Registry file test isolation.
"""

import unittest
import pytest
from core.database import MockNeo4jDriver
from core.registry import RegistryManager, DEFAULT_REGISTRY
from services.remediation_simulator import (
    _compute_uncapped_score_from_smells,
    _find_best_remediation_target,
    GraphEdit,
    RemediationSimulator
)
from services.smell_detector import SmellDetector
from services.impact_engine import ImpactEngine
from services.git_analyzer import ChangeInfo


class WhatIfScoringRegressionTests(unittest.TestCase):
    """Verify after_score is deterministic and does not distort when raw_before > 100."""

    def test_after_score_deterministic_regardless_of_before_magnitude(self):
        """
        Before=90, After=50 -> reports after_score=50.0
        Before=130, After=50 -> reports after_score=50.0
        The after-score should always simply be round(min(100.0, raw_after), 1).
        """
        from services.remediation_simulator import _calculate_simulation_metrics

        # Weights: circular_dependency=30, shared_database=20, hub_and_spoke=20, bottleneck_service=20
        # 130 pts: circular_dependency(30*3=90) + shared_database(20*2=40) = 130
        smells_130 = {
            "circular_dependency": 3,
            "shared_database": 2
        }
        self.assertEqual(_compute_uncapped_score_from_smells(smells_130), 130.0)

        # 90 pts: circular_dependency(30*1=30) + shared_database(20*2=40) + hub_and_spoke(20*1=20) = 90
        smells_90 = {
            "circular_dependency": 1,
            "shared_database": 2,
            "hub_and_spoke": 1
        }
        self.assertEqual(_compute_uncapped_score_from_smells(smells_90), 90.0)

        # 50 pts: circular_dependency(30*1=30) + shared_database(20*1=20) = 50
        smells_50 = {
            "circular_dependency": 1,
            "shared_database": 1
        }
        self.assertEqual(_compute_uncapped_score_from_smells(smells_50), 50.0)

        # Case 1: Before=90, After=50
        b1, a1, red1, meas1, msg1 = _calculate_simulation_metrics(smells_90, smells_50, edits=[])
        self.assertEqual(b1, 90.0)
        self.assertEqual(a1, 50.0)
        self.assertEqual(red1, 40.0)
        self.assertTrue(meas1)

        # Case 2: Before=130, After=50
        b2, a2, red2, meas2, msg2 = _calculate_simulation_metrics(smells_130, smells_50, edits=[])
        self.assertEqual(b2, 100.0)  # Capped at 100
        self.assertEqual(a2, 50.0)   # MUST be 50.0, NOT 38.5!
        self.assertEqual(red2, 50.0)  # 100.0 - 50.0 on the 0-100 scale
        self.assertTrue(meas2)

    def test_after_score_when_both_before_and_after_exceed_cap(self):
        """When raw_before=140 and raw_after=110, both cap at 100.0, reduction=0.0, measurable_change=True."""
        from services.remediation_simulator import _calculate_simulation_metrics
        smells_140 = {"circular_dependency": 4, "hub_and_spoke": 1}  # 30*4 + 20 = 140
        smells_110 = {"circular_dependency": 3, "shared_database": 1}  # 30*3 + 20 = 110

        b, a, red, meas, msg = _calculate_simulation_metrics(smells_140, smells_110, edits=[])
        self.assertEqual(b, 100.0)
        self.assertEqual(a, 100.0)
        self.assertEqual(red, 0.0)
        self.assertTrue(meas)


class ChattyCircularExcludePairsTests(unittest.IsolatedAsyncioTestCase):
    """Verify 2-node cycles do not double-count as Chatty Communication."""

    async def test_exclude_pairs_prevents_double_count(self):
        detector = SmellDetector()
        detector.driver = MockNeo4jDriver()

        # Synthetic dependency set with a 2-node cycle: svc-a <-> svc-b
        test_deps = [
            {"from": "svc-a", "to": "svc-b", "type": "http", "endpoint": "/b"},
            {"from": "svc-b", "to": "svc-a", "type": "http", "endpoint": "/a"},
        ]
        test_services = [{"name": "svc-a"}, {"name": "svc-b"}]

        custom_reg = {
            "project": {"repository_key": "test:test"},
            "services": test_services,
            "dependencies": test_deps
        }
        RegistryManager.save(custom_reg)

        # Circular detector detects cycle
        cycles = await detector._detect_circular_dependencies()
        self.assertTrue(any("svc-a" in c["services"] and "svc-b" in c["services"] for c in cycles))

        cycle_pairs = {tuple(sorted(c["services"])) for c in cycles if len(c.get("services", [])) == 2}
        self.assertIn(("svc-a", "svc-b"), cycle_pairs)

        # Chatty detector with exclude_pairs should NOT flag this single 2-node cycle as chatty
        chatty_excluded = await detector._detect_chatty_communication(exclude_pairs=cycle_pairs)
        self.assertEqual(len(chatty_excluded), 0)

        # Without exclude_pairs, it would have flagged it
        chatty_included = await detector._detect_chatty_communication(exclude_pairs=None)
        self.assertEqual(len(chatty_included), 1)


class SmellDetectorOfflineParityTests(unittest.IsolatedAsyncioTestCase):
    """Verify all structural smell detectors work under MockNeo4jDriver using in-memory fallbacks."""

    async def test_all_smells_detectable_under_mock_neo4j(self):
        detector = SmellDetector()
        detector.driver = MockNeo4jDriver()
        self.assertTrue(detector._is_mock())

        # Use the default demo registry
        RegistryManager.save(DEFAULT_REGISTRY)

        # 1. Circular dependencies fallback
        cycles = await detector._detect_circular_dependencies()
        self.assertGreaterEqual(len(cycles), 1, "Circular dependencies should detect 2-node cycles in demo fleet")

        # 2. Bottleneck services fallback
        bottlenecks = await detector._detect_bottleneck_services()
        self.assertGreaterEqual(len(bottlenecks), 1, "order-service should be detected as bottleneck in demo fleet")
        self.assertEqual(bottlenecks[0]["services"], ["order-service"])

        # 3. Shared database fallback
        shared_db = await detector._detect_shared_database()
        self.assertGreaterEqual(len(shared_db), 1)

        # 4. Missing circuit breaker fallback
        cbs = await detector._detect_missing_circuit_breaker()
        self.assertGreaterEqual(len(cbs), 1)

        # 5. Hub and spoke fallback
        hubs = await detector._detect_hub_and_spoke()
        self.assertGreaterEqual(len(hubs), 1)

        # 6. Dependency explosion from snapshots
        explosions = await detector._detect_dependency_explosion()
        self.assertGreaterEqual(len(explosions), 1)

        # 7. API instability from snapshots
        instability = await detector._detect_api_instability()
        self.assertGreaterEqual(len(instability), 1)

        # Full run: detect_all_smells produces rich results without live Neo4j
        all_smells = await detector.detect_all_smells()
        self.assertGreaterEqual(len(all_smells), 6)


class DegreeBasedCoreServicesTests(unittest.TestCase):
    """Verify core services are determined by graph degree centrality rather than static name lists."""

    def test_core_services_determined_by_centrality(self):
        engine = ImpactEngine()
        RegistryManager.save(DEFAULT_REGISTRY)

        core = engine._get_core_services()
        # In the demo fleet, order-service has the highest in-degree (3)
        self.assertIn("order-service", core)
        # peripheral or disconnected services should not be core
        self.assertNotIn("inventory-service", core)
        self.assertNotIn("payment-service", core)

        # Test impact check matches order-service
        order_change = [ChangeInfo(file_path="services/order_service/main.py", change_type="modified", diff_content="", additions=1, deletions=0, old_content="", new_content="", ast_metadata={})]
        self.assertTrue(engine._has_core_service_impact(order_change))

        # Peripheral service does not trigger core bonus
        peripheral_change = [ChangeInfo(file_path="services/inventory_service/main.py", change_type="modified", diff_content="", additions=1, deletions=0, old_content="", new_content="", ast_metadata={})]
        self.assertFalse(engine._has_core_service_impact(peripheral_change))


class DynamicRemediationTargetTests(unittest.TestCase):
    """Verify _find_best_remediation_target returns empty string rather than 'api-gateway' when no candidate exists."""

    def test_no_candidate_returns_empty(self):
        # Empty registry
        RegistryManager.save({
            "project": {"repository_key": "empty:empty"},
            "services": [{"name": "lone-service"}],
            "dependencies": []
        })

        target = _find_best_remediation_target("lone-service")
        self.assertEqual(target, "")
        self.assertNotEqual(target, "api-gateway")
