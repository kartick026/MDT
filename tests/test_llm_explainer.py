import unittest
from unittest.mock import AsyncMock, MagicMock, patch

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

    async def test_hosted_profile_never_invokes_model_provider(self):
        from core.config import settings
        client = MagicMock()
        client.chat.completions.create = AsyncMock()
        self.explainer.client = client
        with patch.object(settings, "RUNTIME_PROFILE", "hosted"):
            await self.explainer.explain([], ["a"], 50, {})
            await self.explainer.suggest_remediation(["a"], [], 50)
            await self.explainer.suggest_remediation_with_edits([], ["a"], [], 50)
        client.chat.completions.create.assert_not_called()

    async def test_owned_project_disables_even_a_preexisting_provider_client(self):
        from core.registry import RegistryManager
        client = MagicMock()
        client.chat.completions.create = AsyncMock()
        self.explainer.client = client
        with RegistryManager.use_snapshot({"services": [], "dependencies": []}, "owned-project"):
            await self.explainer.explain([], ["a"], 50, {})
            await self.explainer.suggest_remediation(["a"], [], 50)
            await self.explainer.suggest_remediation_with_edits([], ["a"], [], 50)
        client.chat.completions.create.assert_not_called()

    def test_fallback_proposals_are_grouped_by_finding_not_guessed_edit_count(self):
        from core.registry import RegistryManager
        from domain.architecture import registry_snapshot, detect_smells
        from services.remediation_simulator import apply_snapshot_edits, GraphEdit
        data = {"services": [{"name": name} for name in ("a", "b", "c", "d")],
                "dependencies": [{"from": "a", "to": n} for n in ("b", "c", "d")]}
        with RegistryManager.use_snapshot(data, "test"):
            snapshot = registry_snapshot()
            smells = detect_smells(snapshot)
            fixes = self.explainer._fallback_remediation_with_edits(smells)
            self.assertEqual(len(fixes), len(smells))
            for finding, fix in zip(smells, fixes):
                self.assertEqual(fix["finding_id"], finding["id"])
                apply_snapshot_edits(snapshot, [GraphEdit(**e) for e in fix["edits"]])
