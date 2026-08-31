import unittest
from unittest.mock import AsyncMock, patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from schemas.analysis import SeverityLevel
from services.impact_engine import ImpactEngine, RiskFactors
from services.git_analyzer import ChangeInfo

class ImpactEngineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = ImpactEngine()
        
    def test_has_core_service_impact(self):
        changes = [ChangeInfo(file_path="services/payment_service/main.py", change_type="modified", diff_content="", additions=10, deletions=0, old_content="", new_content="", ast_metadata={})]
        self.assertTrue(self.engine._has_core_service_impact(changes))
        
        changes_non_core = [ChangeInfo(file_path="services/some_other_service/main.py", change_type="modified", diff_content="", additions=10, deletions=0, old_content="", new_content="", ast_metadata={})]
        self.assertFalse(self.engine._has_core_service_impact(changes_non_core))

    def test_has_api_changes(self):
        changes = [ChangeInfo(file_path="services/payment_service/api.py", change_type="modified", diff_content="", additions=10, deletions=0, old_content="", new_content="", ast_metadata={})]
        self.assertTrue(self.engine._has_api_changes(changes))
        
        changes_non_api = [ChangeInfo(file_path="services/payment_service/utils.py", change_type="modified", diff_content="", additions=10, deletions=0, old_content="", new_content="", ast_metadata={})]
        self.assertFalse(self.engine._has_api_changes(changes_non_api))

    def test_compute_base_risk(self):
        # file_count (2 * 5 = 10)
        # api_changes (25)
        # core_service (30)
        # dependency_depth (2 * 5 = 10)
        # Total = 75
        factors = RiskFactors(
            file_count=2,
            core_service_impact=True,
            api_changes=True,
            dependency_depth=2,
            semantic_risk=0.0
        )
        score = self.engine._compute_base_risk(factors)
        self.assertEqual(75, score)

    def test_get_severity(self):
        self.assertEqual(SeverityLevel.LOW, self.engine._get_severity(20))
        self.assertEqual(SeverityLevel.MEDIUM, self.engine._get_severity(40))
        self.assertEqual(SeverityLevel.HIGH, self.engine._get_severity(60))
        self.assertEqual(SeverityLevel.CRITICAL, self.engine._get_severity(80))

    def test_compute_confidence(self):
        # No services
        self.assertEqual(0.5, self.engine._compute_confidence([], 0))
        # Static depth (0)
        self.assertEqual(0.70, self.engine._compute_confidence(["service-a"], 0))
        # Real Neo4j depth (2) -> 0.75 + 0.1 = 0.85
        self.assertEqual(0.85, self.engine._compute_confidence(["service-a"], 2))
