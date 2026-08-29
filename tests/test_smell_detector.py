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
