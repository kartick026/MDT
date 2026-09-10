import unittest
from unittest.mock import AsyncMock, patch

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from services.dependency_graph import DependencyGraph, _infer_service_from_path  # type: ignore

MOCK_TEST_DEPS = [
    {"from": "order-service", "to": "user-service", "type": "http", "endpoint": "/users/{user_id}"},
    {"from": "payment-service", "to": "order-service", "type": "http", "endpoint": "/orders/{order_id}"},
    {"from": "notification-service", "to": "order-service", "type": "http", "endpoint": "/orders/{order_id}"},
    {"from": "notification-service", "to": "payment-service", "type": "http", "endpoint": "/payments/{payment_id}"},
]

class DependencyGraphTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.graph = DependencyGraph()
        self.graph.driver = None # force static mode for tests
        self.patcher = patch("core.registry.RegistryManager.get_dependencies", return_value=MOCK_TEST_DEPS)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_infer_service_from_path(self):
        self.assertEqual("payment-service", _infer_service_from_path("services/payment_service/main.py"))
        self.assertEqual("user-service", _infer_service_from_path("services/user_service/db.py"))
        self.assertIsNone(_infer_service_from_path("frontend/src/App.jsx"))

    def test_static_dependency_chain(self):
        chain = self.graph._static_dependency_chain("notification-service")
        self.assertEqual(2, len(chain))
        self.assertTrue(any(c["to"] == "order-service" for c in chain))
        self.assertTrue(any(c["to"] == "payment-service" for c in chain))

    def test_get_dependants_from_static_map(self):
        # user-service is depended on by order, payment, and notification transitively
        dependants = self.graph._get_dependants_from_static_map("user-service")
        self.assertIn("user-service", dependants)
        self.assertIn("order-service", dependants)
        self.assertIn("payment-service", dependants)
        self.assertIn("notification-service", dependants)
        self.assertEqual(4, len(dependants))

        # payment-service is depended on by notification-service
        dependants_payment = self.graph._get_dependants_from_static_map("payment-service")
        self.assertIn("payment-service", dependants_payment)
        self.assertIn("notification-service", dependants_payment)
        self.assertEqual(2, len(dependants_payment))
