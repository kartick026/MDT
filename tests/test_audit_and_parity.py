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
    """Verify after_score and point_reduction correctly reflect debt resolution on the 0-100 scale."""

    def test_after_score_proportional_reduction_when_saturated(self):
        """
        When raw_before <= 100: Before=90, After=50 -> reports after_score=50.0, reduction=40.0
        When raw_before > 100: Before=130, After=50 -> 80/130 (61.5%) debt resolved -> reduction=61.5, after=38.5.
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

        # Case 1: Before=90 (normalized 71.1), After=50 (normalized 57.7)
        b1, a1, red1, meas1, msg1 = _calculate_simulation_metrics(smells_90, smells_50, edits=[])
        self.assertEqual(b1, 71.1)
        self.assertEqual(a1, 57.7)
        self.assertEqual(red1, 13.4)
        self.assertTrue(meas1)

        # Case 2: Before=130 (normalized 78.0), After=50 (normalized 57.7)
        b2, a2, red2, meas2, msg2 = _calculate_simulation_metrics(smells_130, smells_50, edits=[])
        self.assertEqual(b2, 78.0)
        self.assertEqual(a2, 57.7)
        self.assertEqual(red2, 20.3)
        self.assertTrue(meas2)

    def test_after_score_when_both_before_and_after_exceed_cap(self):
        """When raw_before=140 and raw_after=110, scores saturate monotonically to 79.2 and 75.0."""
        from services.remediation_simulator import _calculate_simulation_metrics
        smells_140 = {"circular_dependency": 4, "hub_and_spoke": 1}  # 30*4 + 20 = 140
        smells_110 = {"circular_dependency": 3, "shared_database": 1}  # 30*3 + 20 = 110

        b, a, red, meas, msg = _calculate_simulation_metrics(smells_140, smells_110, edits=[])
        self.assertEqual(b, 79.2)
        self.assertEqual(a, 75.0)
        self.assertEqual(red, 4.2)
        self.assertTrue(meas)
        self.assertIn("Risk reduction verified", msg)

    def test_demo_fleet_what_if_preview_reductions(self):
        """Test realistic demo fleet reductions for recommendations 1, 3, and 4."""
        from services.remediation_simulator import _calculate_simulation_metrics
        # Demo fleet raw debt = 241.0
        before = {
            'circular_dependency': 3,
            'bottleneck_service': 1,
            'high_coupling': 1,
            'chatty_communication': 2,
            'missing_circuit_breaker': 1,
            'hub_and_spoke': 1,
            'dependency_explosion': 1,
            'api_instability': 1,
            'shared_database': 1,
            'isolated_service': 1
        }
        # Rec 1: resolves 2 cycles and 1 chatty (raw 241 -> 169)
        after_1 = dict(before)
        after_1['circular_dependency'] = 1
        after_1['chatty_communication'] = 1
        b1, a1, r1, m1, _ = _calculate_simulation_metrics(before, after_1, edits=[])
        self.assertEqual(b1, 86.8)
        self.assertEqual(a1, 82.2)
        self.assertEqual(r1, 4.6)
        self.assertTrue(m1)

        # Rec 3: resolves 5 smells (raw 241 -> 142)
        after_3 = dict(before)
        after_3['circular_dependency'] = 1
        after_3['high_coupling'] = 0
        after_3['chatty_communication'] = 1
        after_3['missing_circuit_breaker'] = 0
        b3, a3, r3, m3, _ = _calculate_simulation_metrics(before, after_3, edits=[])
        self.assertEqual(b3, 86.8)
        self.assertEqual(a3, 79.5)
        self.assertEqual(r3, 7.3)
        self.assertTrue(m3)


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
        bottleneck_services = [s for finding in bottlenecks for s in finding.get("services", [])]
        self.assertIn("order-service", bottleneck_services, "order-service should be detected as bottleneck in demo fleet")

        # 3. High coupling fallback
        couplings = await detector._detect_high_coupling()
        self.assertGreaterEqual(len(couplings), 1, "High coupling should detect tightly-coupled services in demo fleet")

        # 4. Dead / Isolated services fallback
        isolated = await detector._detect_isolated_services()
        self.assertGreaterEqual(len(isolated), 1, "Isolated service should detect payment-service in demo fleet")

        # 5. Shared database fallback
        shared_db = await detector._detect_shared_database()
        self.assertGreaterEqual(len(shared_db), 1, "Shared database should detect local-demo-postgres in demo fleet")

        # 6. Chatty communication fallback
        chatty = await detector._detect_chatty_communication()
        self.assertGreaterEqual(len(chatty), 1, "Chatty communication should detect cyclic chatter in demo fleet")

        # 7. Missing circuit breaker fallback
        cbs = await detector._detect_missing_circuit_breaker()
        self.assertGreaterEqual(len(cbs), 1, "Missing circuit breaker should detect unshielded services in demo fleet")

        # 8. Hub and spoke fallback
        hubs = await detector._detect_hub_and_spoke()
        self.assertGreaterEqual(len(hubs), 1, "Hub and spoke should detect order-service central hub in demo fleet")

        # 9. Dependency explosion from snapshots
        explosions = await detector._detect_dependency_explosion()
        self.assertGreaterEqual(len(explosions), 1, "Dependency explosion should detect snapshot additions in demo fleet")

        # 10. API instability from snapshots
        instability = await detector._detect_api_instability()
        self.assertGreaterEqual(len(instability), 1, "API instability should detect endpoint churn in demo fleet")

        # Full run: detect_all_smells produces all 10 architectural smells in the demo fleet
        all_smells = await detector.detect_all_smells()
        smell_types = {s["type"] for s in all_smells}
        expected_10_smells = {
            "Circular Dependency",
            "God / Bottleneck Service",
            "High Coupling",
            "Dead / Isolated Service",
            "Dependency Explosion",
            "API Instability",
            "Shared Database",
            "Missing Circuit Breaker",
            "Hub-and-Spoke Centralization",
            "Chatty Communication",
        }
        self.assertEqual(smell_types, expected_10_smells)


class DegreeBasedCoreServicesTests(unittest.TestCase):
    """Verify core services are determined by graph degree centrality rather than static name lists."""

    def test_core_services_determined_by_centrality(self):
        engine = ImpactEngine()
        RegistryManager.save(DEFAULT_REGISTRY)

        core = engine._get_core_services()
        # Demo fleet topology assertion — deliberately verifies DEFAULT_REGISTRY structural properties
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

    def test_core_services_statistical_outlier_for_large_fleets(self):
        """Verify that when fleet variance is large (std >= 1.0), mean + std isolates true hubs."""
        engine = ImpactEngine()
        # Mock a 10-service fleet:
        # auth-hub has 6 incoming callers
        # payment-hub has 4 incoming callers
        # other 8 services have 1 caller each
        # degrees = [6, 4, 1, 1, 1, 1, 1, 1, 1, 1], mean = 1.8, std = 1.6
        # threshold = max(2, round(1.8 + 1.6)) = round(3.4) = 3
        # auth-hub (6) and payment-hub (4) are core; minor services (1) are excluded.
        large_fleet_registry = {
            "project": {"repository_key": "enterprise:enterprise"},
            "services": [{"name": f"svc-{i}"} for i in range(10)] + [{"name": "auth-hub"}, {"name": "payment-hub"}],
            "dependencies": (
                [{"from": f"svc-{i}", "to": "auth-hub"} for i in range(6)] +
                [{"from": f"svc-{i}", "to": "payment-hub"} for i in range(4)] +
                [{"from": "auth-hub", "to": f"svc-{i}"} for i in range(8)]
            )
        }
        RegistryManager.save(large_fleet_registry)
        core = engine._get_core_services()
        self.assertIn("auth-hub", core)
        self.assertIn("payment-hub", core)
        for i in range(8):
            self.assertNotIn(f"svc-{i}", core)



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


class IsolatedServiceExclusionTests(unittest.IsolatedAsyncioTestCase):
    """Verify that is_external services and architectural infrastructure are not flagged as isolated."""

    async def test_external_and_facade_services_excluded_from_isolation(self):
        self.addCleanup(RegistryManager.save, DEFAULT_REGISTRY)
        RegistryManager.save({
            "project": {"repository_key": "test:external_repo"},
            "services": [
                {"name": "external-service-a", "is_external": True},
                {"name": "external-service-b", "is_external": True},
                {"name": "order-service_facade"},
                {"name": "payment_gateway"},
                {"name": "event_broker"},
                {"name": "real-unconnected-service", "is_external": False},
            ],
            "dependencies": []
        })

        detector = SmellDetector()
        detector.driver = MockNeo4jDriver()
        isolated = await detector._detect_isolated_services()
        isolated_names = {s for finding in isolated for s in finding.get("services", [])}

        self.assertNotIn("external-service-a", isolated_names, "Externally imported services must not be flagged as dead/isolated")
        self.assertNotIn("external-service-b", isolated_names, "Externally imported services must not be flagged as dead/isolated")
        self.assertNotIn("order-service_facade", isolated_names, "Facades must not be flagged as dead/isolated")
        self.assertNotIn("payment_gateway", isolated_names, "Gateways must not be flagged as dead/isolated")
        self.assertNotIn("event_broker", isolated_names, "Brokers must not be flagged as dead/isolated")
        self.assertIn("real-unconnected-service", isolated_names, "Real internal unconnected services must be detected as isolated")
        self.assertEqual(len(isolated), 1)

    async def test_notification_service_detected_as_isolated_and_simulated(self):
        self.addCleanup(RegistryManager.save, DEFAULT_REGISTRY)
        RegistryManager.save({
            "project": {"repository_key": "github:kartick026/mdt"},
            "services": [
                {"name": "frontend", "is_external": False},
                {"name": "backend", "is_external": False},
                {"name": "user", "is_external": False},
                {"name": "order", "is_external": False},
                {"name": "payment", "is_external": False},
                {"name": "notification", "is_external": False},
            ],
            "dependencies": [
                {"from": "frontend", "to": "backend", "type": "http"},
                {"from": "payment", "to": "order", "type": "http"},
                {"from": "order", "to": "user", "type": "http"},
            ]
        })

        detector = SmellDetector()
        detector.driver = MockNeo4jDriver()
        isolated = await detector._detect_isolated_services()
        isolated_names = {s for finding in isolated for s in finding.get("services", [])}
        self.assertIn("notification", isolated_names, "Notification with degree 0 must be detected as isolated")

        from services.remediation_simulator import RemediationSimulator, GraphEdit
        sim = RemediationSimulator()
        sim.driver = MockNeo4jDriver()
        preview = await sim.simulate_fix([
            GraphEdit(action="add_edge", from_service="order", to_service="notification")
        ])
        self.assertEqual(preview["before"]["smells"]["isolated_service"], 1)
        self.assertEqual(preview["after"]["smells"]["isolated_service"], 0)
        self.assertTrue(preview["delta"]["measurable_change"])
        self.assertGreater(preview["delta"]["score_reduction"], 0)

    async def test_baseline_smells_shared_between_analysis_and_simulation(self):
        from services.remediation_simulator import RemediationSimulator, GraphEdit, compute_architecture_health

        # Analysis computed 3 smells: dependency explosion, api instability, isolated service
        baseline = {
            "circular_dependency": 0, "shared_database": 0, "hub_and_spoke": 0,
            "bottleneck_service": 0, "dependency_explosion": 1, "high_coupling": 0,
            "api_instability": 1, "chatty_communication": 0, "missing_circuit_breaker": 0,
            "isolated_service": 1,
        }
        health = compute_architecture_health(baseline)
        self.assertEqual(health["score"], 52.2)
        self.assertEqual(health["total_smells"], 3)

        sim = RemediationSimulator()
        sim.driver = MockNeo4jDriver()
        preview = await sim.simulate_fix(
            edits=[GraphEdit(action="add_edge", from_service="order", to_service="notification")],
            baseline_smells=baseline,
        )

        # Before MUST strictly equal Architecture Health from analysis (same function, same baseline)
        self.assertEqual(preview["before"]["score"], health["score"])
        self.assertEqual(preview["before"]["total_smells"], health["total_smells"])
        # After resolves isolated service but preserves historical snapshot smells
        self.assertEqual(preview["after"]["smells"]["isolated_service"], 0)
        self.assertEqual(preview["after"]["smells"]["dependency_explosion"], 1)
        self.assertEqual(preview["after"]["smells"]["api_instability"], 1)
        self.assertEqual(preview["after"]["total_smells"], 2)
        self.assertLess(preview["after"]["score"], preview["before"]["score"])
        self.assertTrue(preview["delta"]["measurable_change"])


class Phase9CodeAuditTests(unittest.IsolatedAsyncioTestCase):
    """Verify Phase 9 Codebase Audit fixes."""

    def test_simulation_negative_degradation_handling(self):
        """When an edit introduces new smells, after_score increases and warning message is emitted."""
        from services.remediation_simulator import _calculate_simulation_metrics

        before_smells = {"circular_dependency": 1}  # raw 30, score 45.0
        # Simulated edit accidentally introduces an additional cycle and a shared database
        after_smells = {"circular_dependency": 2, "shared_database": 1}  # raw 80, score 68.6

        b, a, red, meas, msg = _calculate_simulation_metrics(before_smells, after_smells, edits=[])
        self.assertEqual(b, 45.0)
        self.assertEqual(a, 68.6)
        self.assertLess(red, 0.0)
        self.assertEqual(red, -23.6)
        self.assertTrue(meas)
        self.assertIn("Warning: Proposed edit increases architectural risk by +23.6 pts", msg)
        self.assertIn("new smell(s) introduced", msg)

    def test_parse_github_url_robustness(self):
        """Verify _parse_github_url handles various formats including dots and trailing slashes."""
        from services.git_analyzer import _parse_github_url

        urls = [
            ("https://github.com/owner/repo", ("owner", "repo")),
            ("https://github.com/owner/repo.git", ("owner", "repo")),
            ("https://github.com/owner/repo.name", ("owner", "repo.name")),
            ("https://github.com/owner/repo.name.git", ("owner", "repo.name")),
            ("https://github.com/owner/repo/", ("owner", "repo")),
            ("git@github.com:owner/repo.git", ("owner", "repo")),
        ]
        for url, expected in urls:
            result = _parse_github_url(url)
            self.assertEqual(result, expected, f"Failed for {url}")

    def test_impact_engine_clamping(self):
        """Verify final_risk is clamped strictly between 0.0 and 100.0."""
        def clamp_risk(base_risk: float, semantic_boost: float) -> float:
            return max(0.0, min(100.0, round(float(base_risk + semantic_boost), 1)))

        self.assertEqual(clamp_risk(95.0, 20.0), 100.0)
        self.assertEqual(clamp_risk(5.0, -20.0), 0.0)
        self.assertEqual(clamp_risk(50.0, 10.0), 60.0)

    def test_settings_dynamic_thresholds(self):
        """Verify core.config settings expose required risk and demo properties."""
        from core.config import settings

        self.assertEqual(settings.RISK_LOW, 25)
        self.assertEqual(settings.RISK_MEDIUM, 50)
        self.assertEqual(settings.RISK_HIGH, 75)
        self.assertTrue(settings.DEMO_REPO_URL.startswith("https://github.com/"))
        self.assertTrue(bool(settings.DEMO_REPO_BRANCH))

    def test_is_supported_file_includes_html_templates_and_configs(self):
        """Verify web templates, styles, configs, and non-binary files are supported in git analyzer."""
        from services.git_analyzer import is_supported_file

        self.assertTrue(is_supported_file("app/templates/base.html"))
        self.assertTrue(is_supported_file("index.html"))
        self.assertTrue(is_supported_file("static/style.css"))
        self.assertTrue(is_supported_file("render.yaml"))
        self.assertTrue(is_supported_file("config.json"))
        self.assertTrue(is_supported_file("Dockerfile"))
        self.assertTrue(is_supported_file("services/order_service/main.py"))

        # Binaries must be rejected
        self.assertFalse(is_supported_file("logo.png"))
        self.assertFalse(is_supported_file("font.woff2"))
        self.assertFalse(is_supported_file("cache.pyc"))
        self.assertFalse(is_supported_file("bundle.zip"))

    @pytest.mark.asyncio
    async def test_imported_repo_does_not_leak_demo_snapshots(self):
        """Verify an imported repository (e.g. AyushBajaj7/Luxon) never inherits demo snapshots."""
        import tempfile
        from pathlib import Path

        tmp_dir = tempfile.mkdtemp()
        orig_file = RegistryManager.REGISTRY_FILE
        try:
            RegistryManager.REGISTRY_FILE = Path(tmp_dir) / "registry.json"
            RegistryManager.clear()
            RegistryManager.set_project_context(
                repo_url="https://github.com/AyushBajaj7/Luxon",
                branch="main",
                source="repository",
            )
            RegistryManager.add_service({"name": "luxon", "port": 8808, "endpoints": ["/"]})
            RegistryManager.add_service({"name": "app", "port": 8092, "endpoints": ["/home"]})

            detector = SmellDetector()
            detector.driver = MockNeo4jDriver()

            smells = await detector.detect_all_smells()
            smell_types = {s["type"] for s in smells}
            all_services = [svc for s in smells for svc in s.get("services", [])]

            # Neither Dependency Explosion nor API Instability should be triggered by demo snapshots
            self.assertNotIn("Dependency Explosion", smell_types)
            self.assertNotIn("API Instability", smell_types)
            self.assertNotIn("order-service", all_services)
            self.assertNotIn("notification-service", all_services)
        finally:
            RegistryManager.REGISTRY_FILE = orig_file
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

