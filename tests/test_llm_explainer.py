import unittest
from unittest.mock import AsyncMock

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from services.llm_explainer import LLMExplainer
from services.git_analyzer import ChangeInfo

class LLMExplainerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.explainer = LLMExplainer()
        self.explainer.client = None # force fallback

    def test_fallback_explanation(self):
        changes = [ChangeInfo(file_path="services/payment_service/main.py", change_type="modified", diff_content="", additions=10, deletions=0, old_content="", new_content="", ast_metadata={})]
        impacted_services = ["payment-service", "notification-service"]
        
        explanation = self.explainer._fallback_explanation(changes, impacted_services, 75.0)
        self.assertIn("Critical risk score", explanation)
        self.assertIn("payment_service/main.py", explanation)
        self.assertIn("payment-service, notification-service", explanation)

    def test_fallback_remediation(self):
        impacted_services = ["payment-service", "notification-service"]
        suggestions = self.explainer._fallback_remediation(impacted_services, 80.0)
        
        self.assertTrue(any("code review" in s for s in suggestions))
        self.assertTrue(any("Notify teams" in s for s in suggestions))
        self.assertTrue(any("integration tests" in s for s in suggestions))
        
    def test_severity_label(self):
        self.assertEqual("Low", self.explainer._get_severity_label(20))
        self.assertEqual("Medium", self.explainer._get_severity_label(40))
        self.assertEqual("High", self.explainer._get_severity_label(60))
        self.assertEqual("Critical", self.explainer._get_severity_label(80))
