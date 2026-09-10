import unittest
import sys
import os
from pathlib import Path

# Ensure backend is on sys.path
backend_dir = str(Path(__file__).parent.parent / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.registry import DEFAULT_REGISTRY, RegistryManager, ServiceRegistry
from core.database import (
    check_neo4j_health,
    check_chroma_health,
    MockNeo4jDriver,
    MockNeo4jSession,
    MockNeo4jTransaction,
)


class DatabaseAndRegistryTests(unittest.TestCase):
    def setUp(self):
        RegistryManager.reload()

    def test_registry_validation_valid_service(self):
        valid = {
            "name": "billing-service",
            "port": 8010,
            "url": "http://billing-service:8010",
            "description": "Billing service"
        }
        RegistryManager.validate_service(valid)

    def test_registry_validation_invalid_name(self):
        with self.assertRaises(ValueError):
            RegistryManager.validate_service({"name": ""})

        with self.assertRaises(ValueError):
            RegistryManager.validate_service({"name": "invalid name with spaces!"})

    def test_registry_validation_invalid_port(self):
        with self.assertRaises(ValueError):
            RegistryManager.validate_service({"name": "good-service", "port": 70000})

        with self.assertRaises(ValueError):
            RegistryManager.validate_service({"name": "good-service", "port": "not-a-port"})

    def test_registry_in_memory_cache(self):
        s1 = RegistryManager.get_services()
        s2 = RegistryManager.get_services()
        self.assertEqual(len(s1), len(s2))
        self.assertIsNotNone(RegistryManager._cache)

    def test_repository_key_normalizes_github_url_variants(self):
        self.assertEqual(
            RegistryManager.repository_key("git@github.com:Kartick026/MDT.git"),
            "github:kartick026/mdt",
        )

    def test_local_demo_fleet_contains_evidence_for_every_detector(self):
        names = {service["name"] for service in DEFAULT_REGISTRY["services"]}
        edges = {(edge["from"], edge["to"]) for edge in DEFAULT_REGISTRY["dependencies"]}
        history = RegistryManager.get_local_demo_smell_history()

        self.assertEqual(names, {"user-service", "order-service", "payment-service", "notification-service"})
        self.assertNotIn("local-demo-postgres", names)
        self.assertIn(("user-service", "order-service"), edges)
        self.assertIn(("order-service", "user-service"), edges)
        self.assertIn(("user-service", "local-demo-postgres"), edges)
        self.assertIn(("notification-service", "local-demo-postgres"), edges)
        self.assertEqual(len(history["dependency_snapshots"]), 2)
        self.assertEqual(len(history["api_snapshots"]), 2)
        self.assertEqual(
            RegistryManager.repository_key("https://github.com/kartick026/MDT/"),
            "github:kartick026/mdt",
        )

    def test_service_registry_helper(self):
        registry = ServiceRegistry()
        services_map = registry.list_services()
        self.assertIsInstance(services_map, dict)
        if "user-service" in services_map:
            self.assertEqual(services_map["user-service"]["port"], 8001)

    def test_database_health_checks(self):
        n_health = check_neo4j_health()
        self.assertIn("status", n_health)
        self.assertIn("connected", n_health)

        c_health = check_chroma_health()
        self.assertIn("status", c_health)
        self.assertIn("connected", c_health)

    def test_mock_neo4j_driver_compatibility(self):
        driver = MockNeo4jDriver()
        driver.verify_connectivity()
        session = driver.session()
        self.assertIsInstance(session, MockNeo4jSession)
        tx = session.begin_transaction()
        self.assertIsInstance(tx, MockNeo4jTransaction)
        tx.rollback()
        tx.commit()
        driver.close()


if __name__ == "__main__":
    unittest.main()
