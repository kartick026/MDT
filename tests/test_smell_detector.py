import unittest
from unittest.mock import AsyncMock, patch

from services.smell_detector import SmellDetector
class SmellDetectorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.detector = SmellDetector()
        self.detector.driver = object()

    @patch("services.smell_detector._run_query", new_callable=AsyncMock)
    async def test_dependency_explosion_requires_real_growth(self, run_query):
        run_query.return_value = [
            {"edges": ["a->b", "a->c", "a->d", "a->e"], "created_at": "2026-01-02"},
            {"edges": ["a->b"], "created_at": "2026-01-01"},
        ]

        findings = await self.detector._detect_dependency_explosion()

        self.assertEqual(1, len(findings))
        self.assertEqual("Dependency Explosion", findings[0]["type"])
        self.assertEqual(["a->c", "a->d", "a->e"], findings[0]["evidence"]["added_edges"])

    @patch("services.smell_detector._run_query", new_callable=AsyncMock)
    async def test_api_instability_detects_removed_endpoint(self, run_query):
        run_query.return_value = [
            {"service": "orders", "endpoints": ["GET /orders"], "created_at": "2026-01-02"},
            {"service": "orders", "endpoints": ["GET /orders", "POST /orders"], "created_at": "2026-01-01"},
        ]

        findings = await self.detector._detect_api_instability()

        self.assertEqual(1, len(findings))
        self.assertEqual("HIGH", findings[0]["severity"])
        self.assertEqual(["POST /orders"], findings[0]["evidence"]["removed_endpoints"])

    @patch("services.smell_detector._run_query", new_callable=AsyncMock)
    async def test_api_instability_ignores_unchanged_contract(self, run_query):
        run_query.return_value = [
            {"service": "orders", "endpoints": ["GET /orders"], "created_at": "2026-01-02"},
            {"service": "orders", "endpoints": ["GET /orders"], "created_at": "2026-01-01"},
        ]

        self.assertEqual([], await self.detector._detect_api_instability())

    @patch("core.registry.RegistryManager.get_dependencies")
    async def test_shared_database_detection(self, mock_deps):
        mock_deps.return_value = [
            {"from": "order-service", "to": "postgres-db", "type": "database", "endpoint": ":5432"},
            {"from": "payment-service", "to": "postgres-db", "type": "database", "endpoint": ":5432"},
        ]
        findings = await self.detector._detect_shared_database()
        self.assertEqual(1, len(findings))
        self.assertEqual("Shared Database", findings[0]["type"])
        self.assertIn("order-service", findings[0]["services"])
        self.assertIn("payment-service", findings[0]["services"])

    @patch("core.registry.RegistryManager.get_dependencies")
    async def test_chatty_communication_bidirectional(self, mock_deps):
        mock_deps.return_value = [
            {"from": "order-service", "to": "user-service", "type": "http", "endpoint": "/users"},
            {"from": "user-service", "to": "order-service", "type": "http", "endpoint": "/orders"},
        ]
        findings = await self.detector._detect_chatty_communication()
        self.assertEqual(1, len(findings))
        self.assertEqual("Chatty Communication", findings[0]["type"])
        self.assertTrue(findings[0]["evidence"]["bidirectional"])

    @patch("core.registry.RegistryManager.get_services")
    @patch("core.registry.RegistryManager.get_dependencies")
    async def test_missing_circuit_breaker(self, mock_deps, mock_services):
        mock_services.return_value = [
            {"name": "order-service"},
            {"name": "user-service"},
            {"name": "payment-service"},
            {"name": "notification-service"},
            {"name": "inventory-service"},
        ]
        mock_deps.return_value = [
            {"from": "order-service", "to": "user-service", "type": "http"},
            {"from": "order-service", "to": "payment-service", "type": "http"},
            {"from": "order-service", "to": "notification-service", "type": "http"},
            {"from": "order-service", "to": "inventory-service", "type": "http"},
        ]
        findings = await self.detector._detect_missing_circuit_breaker()
        self.assertEqual(1, len(findings))
        self.assertEqual("Missing Circuit Breaker", findings[0]["type"])
        self.assertEqual(["order-service"], findings[0]["services"])

    @patch("core.registry.RegistryManager.get_services")
    @patch("core.registry.RegistryManager.get_dependencies")
    async def test_hub_and_spoke_centralization(self, mock_deps, mock_services):
        mock_services.return_value = [
            {"name": "core-hub"},
            {"name": "service-a"},
            {"name": "service-b"},
            {"name": "service-c"},
            {"name": "service-d"},
            {"name": "service-e"},
        ]
        # core-hub connects to service-a, service-b, service-c, service-d (4 out of 5 other services = 80% > 70%)
        mock_deps.return_value = [
            {"from": "service-a", "to": "core-hub", "type": "http"},
            {"from": "core-hub", "to": "service-b", "type": "http"},
            {"from": "core-hub", "to": "service-c", "type": "http"},
            {"from": "core-hub", "to": "service-d", "type": "http"},
        ]
        findings = await self.detector._detect_hub_and_spoke()
        self.assertEqual(1, len(findings))
        self.assertEqual("Hub-and-Spoke Centralization", findings[0]["type"])
        self.assertEqual(["core-hub"], findings[0]["services"])

    @patch("services.smell_detector._run_query", new_callable=AsyncMock)
    async def test_circular_dependencies(self, run_query):
        run_query.return_value = [
            {"cycle": ["service-a", "service-b", "service-c", "service-a"]}
        ]
        findings = await self.detector._detect_circular_dependencies()
        self.assertEqual(1, len(findings))
        self.assertEqual("Circular Dependency", findings[0]["type"])
        self.assertEqual("CRITICAL", findings[0]["severity"])
        self.assertEqual(["service-a", "service-b", "service-c"], findings[0]["services"])

    @patch("services.smell_detector._run_query", new_callable=AsyncMock)
    async def test_bottleneck_services(self, run_query):
        run_query.return_value = [
            {"name": "heavy-bottleneck", "incoming_count": 5, "outgoing_count": 4}
        ]
        findings = await self.detector._detect_bottleneck_services()
        self.assertEqual(1, len(findings))
        self.assertEqual("God / Bottleneck Service", findings[0]["type"])
        self.assertEqual(["heavy-bottleneck"], findings[0]["services"])

    @patch("services.smell_detector._run_query", new_callable=AsyncMock)
    async def test_high_coupling(self, run_query):
        run_query.return_value = [
            {"name": "tightly-coupled", "dependency_count": 7}
        ]
        findings = await self.detector._detect_high_coupling()
        self.assertEqual(1, len(findings))
        self.assertEqual("High Coupling", findings[0]["type"])
        self.assertEqual(["tightly-coupled"], findings[0]["services"])

    @patch("services.smell_detector._run_query", new_callable=AsyncMock)
    async def test_isolated_services(self, run_query):
        run_query.return_value = [
            {"name": "lonely-service"}
        ]
        findings = await self.detector._detect_isolated_services()
        self.assertEqual(1, len(findings))
        self.assertEqual("Dead / Isolated Service", findings[0]["type"])
        self.assertEqual(["lonely-service"], findings[0]["services"])

    @patch.object(SmellDetector, "_detect_circular_dependencies", new_callable=AsyncMock)
    @patch.object(SmellDetector, "_detect_bottleneck_services", new_callable=AsyncMock)
    @patch.object(SmellDetector, "_detect_high_coupling", new_callable=AsyncMock)
    @patch.object(SmellDetector, "_detect_isolated_services", new_callable=AsyncMock)
    @patch.object(SmellDetector, "_detect_dependency_explosion", new_callable=AsyncMock)
    @patch.object(SmellDetector, "_detect_api_instability", new_callable=AsyncMock)
    @patch.object(SmellDetector, "_detect_shared_database", new_callable=AsyncMock)
    @patch.object(SmellDetector, "_detect_chatty_communication", new_callable=AsyncMock)
    @patch.object(SmellDetector, "_detect_missing_circuit_breaker", new_callable=AsyncMock)
    @patch.object(SmellDetector, "_detect_hub_and_spoke", new_callable=AsyncMock)
    async def test_detect_all_smells_aggregates_all_ten(
        self, m_hub, m_cb, m_chat, m_db, m_api, m_expl, m_iso, m_coup, m_bottle, m_circ
    ):
        m_circ.return_value = [{"type": "Circular Dependency"}]
        m_bottle.return_value = [{"type": "God / Bottleneck Service"}]
        m_coup.return_value = [{"type": "High Coupling"}]
        m_iso.return_value = [{"type": "Dead / Isolated Service"}]
        m_expl.return_value = [{"type": "Dependency Explosion"}]
        m_api.return_value = [{"type": "API Instability"}]
        m_db.return_value = [{"type": "Shared Database"}]
        m_chat.return_value = [{"type": "Chatty Communication"}]
        m_cb.return_value = [{"type": "Missing Circuit Breaker"}]
        m_hub.return_value = [{"type": "Hub-and-Spoke Centralization"}]

        all_smells = await self.detector.detect_all_smells()
        self.assertEqual(10, len(all_smells))
        types = [s["type"] for s in all_smells]
        self.assertIn("Circular Dependency", types)
        self.assertIn("Shared Database", types)
        self.assertIn("Missing Circuit Breaker", types)
        self.assertIn("Hub-and-Spoke Centralization", types)

    @patch("core.registry.RegistryManager.get_dependencies")
    async def test_shared_database_case_insensitive_grouping(self, mock_deps):
        """Case variations like PostgresDB vs postgresdb must group to the same shared DB smell."""
        mock_deps.return_value = [
            {"from": "order-service", "to": "PostgresDB", "type": "database", "endpoint": ":5432"},
            {"from": "payment-service", "to": "postgresdb", "type": "database", "endpoint": ":5432"},
        ]
        findings = await self.detector._detect_shared_database()
        self.assertEqual(1, len(findings))
        self.assertEqual("Shared Database", findings[0]["type"])
        self.assertEqual(["order-service", "payment-service"], sorted(findings[0]["services"]))

    @patch("core.registry.RegistryManager.get_dependencies")
    @patch("core.registry.RegistryManager.get_services")
    async def test_missing_circuit_breaker_does_not_exempt_named_services(self, mock_services, mock_deps):
        """Services named 'order-gateway' without real resilience code must not be exempted."""
        mock_services.return_value = [
            {"name": "order-gateway"},
            {"name": "svc-a"},
            {"name": "svc-b"},
            {"name": "svc-c"},
            {"name": "svc-d"},
        ]
        mock_deps.return_value = [
            {"from": "order-gateway", "to": "svc-a", "type": "http"},
            {"from": "order-gateway", "to": "svc-b", "type": "http"},
            {"from": "order-gateway", "to": "svc-c", "type": "http"},
            {"from": "order-gateway", "to": "svc-d", "type": "http"},
        ]
        findings = await self.detector._detect_missing_circuit_breaker()
        self.assertEqual(1, len(findings))
        self.assertEqual("Missing Circuit Breaker", findings[0]["type"])
        self.assertEqual(["order-gateway"], findings[0]["services"])

    @patch("core.registry.RegistryManager.get_dependencies")
    async def test_chatty_communication_excludes_isolated_2node_cycle(self, mock_deps):
        """Single bidirectional calls already caught as 2-node cycles are not double-counted as chatty."""
        mock_deps.return_value = [
            {"from": "order-service", "to": "user-service", "type": "http"},
            {"from": "user-service", "to": "order-service", "type": "http"},
        ]
        excluded = {("order-service", "user-service")}
        findings = await self.detector._detect_chatty_communication(exclude_pairs=excluded)
        self.assertEqual(0, len(findings))

    def test_circuit_breaker_threshold_mathematical_algorithm(self):
        """Verify dynamic percolation scaling for circuit breaker threshold."""
        from services.smell_detector import calculate_circuit_breaker_threshold

        # Small fleets scale at minimum 2
        self.assertEqual(calculate_circuit_breaker_threshold(2), 2)
        self.assertEqual(calculate_circuit_breaker_threshold(3), 2)
        # Demo fleet (5 services): ceil(sqrt(5)) = 3
        self.assertEqual(calculate_circuit_breaker_threshold(5), 3)
        # Medium fleets
        self.assertEqual(calculate_circuit_breaker_threshold(9), 3)
        self.assertEqual(calculate_circuit_breaker_threshold(10), 4)
        # Large fleet
        self.assertEqual(calculate_circuit_breaker_threshold(25), 5)

        # Statistical outlier modulation with skewed outbound distribution
        # e.g., 5 nodes where one calls 4 and others call 0: mean = 0.8, std ~ 1.6 => ceil(2.4) = 3
        self.assertEqual(calculate_circuit_breaker_threshold(5, [4, 0, 0, 0, 0]), 3)

    def test_hub_and_spoke_threshold_mathematical_algorithm(self):
        """Verify Freeman centrality ratio scaling for hub-and-spoke threshold."""
        from services.smell_detector import calculate_hub_and_spoke_threshold

        # Fewer than 3 nodes cannot form a star hub
        self.assertEqual(calculate_hub_and_spoke_threshold(1), 0)
        self.assertEqual(calculate_hub_and_spoke_threshold(2), 0)
        # 3 nodes: max(2, ceil(0.60 * 2)) = 2
        self.assertEqual(calculate_hub_and_spoke_threshold(3), 2)
        # 4 nodes: max(2, ceil(0.60 * 3)) = 2
        self.assertEqual(calculate_hub_and_spoke_threshold(4), 2)
        # 5 nodes (demo fleet): ceil(0.60 * 4) = 3
        self.assertEqual(calculate_hub_and_spoke_threshold(5), 3)
        # 10 nodes: ceil(0.684 * 9) = 7
        self.assertEqual(calculate_hub_and_spoke_threshold(10), 7)

    @patch("core.registry.RegistryManager.get_dependencies")
    @patch("core.registry.RegistryManager.get_services")
    async def test_hub_and_spoke_ignores_symmetric_clique(self, mock_services, mock_deps):
        """A symmetric mesh/clique where all nodes have equal degree must not trigger hub-and-spoke."""
        mock_services.return_value = [
            {"name": "svc-1"},
            {"name": "svc-2"},
            {"name": "svc-3"},
            {"name": "svc-4"},
        ]
        # Fully connected mesh: every service connects to every other service
        mock_deps.return_value = [
            {"from": "svc-1", "to": "svc-2", "type": "http"},
            {"from": "svc-1", "to": "svc-3", "type": "http"},
            {"from": "svc-1", "to": "svc-4", "type": "http"},
            {"from": "svc-2", "to": "svc-3", "type": "http"},
            {"from": "svc-2", "to": "svc-4", "type": "http"},
            {"from": "svc-3", "to": "svc-4", "type": "http"},
        ]
        findings = await self.detector._detect_hub_and_spoke()
        # All 4 services have degree 3, equal to average degree 3.0. No single hub exists.
        self.assertEqual(0, len(findings))
