import unittest
import sys
from pathlib import Path

# Ensure backend is on sys.path
backend_dir = str(Path(__file__).parent.parent / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.retrieval import (
    _chunk_content,
    _tfidf_embed,
    RetrievalEngine,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
)


class RetrievalEngineTests(unittest.IsolatedAsyncioTestCase):
    def test_chunk_content(self):
        # Create 120 lines of dummy code
        lines = [f"line_{i} = {i}" for i in range(1, 121)]
        content = "\n".join(lines)
        chunks = _chunk_content(content, "services/test.py")

        self.assertGreater(len(chunks), 1)
        first_chunk = chunks[0]
        self.assertEqual(first_chunk["start_line"], 1)
        self.assertEqual(first_chunk["end_line"], CHUNK_SIZE)
        self.assertIn("chunk_id", first_chunk)

    def test_tfidf_embed_produces_normalized_vectors(self):
        texts = [
            "def process_order(user_id, order_id): return user_id",
            "class PaymentGateway: def pay(self, amount): pass",
            "import os, sys, json"
        ]
        vectors = _tfidf_embed(texts)
        self.assertEqual(3, len(vectors))
        self.assertTrue(len(vectors[0]) > 0)
        
        # Test unit length / normalization: sqrt(sum(v^2)) ≈ 1.0
        norm = sum(v * v for v in vectors[0]) ** 0.5
        self.assertAlmostEqual(1.0, norm, places=3)

    def test_purge_collection_graceful_handling(self):
        engine = RetrievalEngine()
        # Even if ChromaDB is not connected or local, purge_collection should return a boolean without crashing
        result = engine.purge_collection()
        self.assertIsInstance(result, bool)

    def test_compute_risk_modifier(self):
        engine = RetrievalEngine()
        metadatas = [
            {"risk_score": 80.0},
            {"risk_score": 60.0},
        ]
        distances = [0.1, 0.2]
        modifier = engine._compute_risk_modifier(metadatas, distances)
        self.assertGreater(modifier, 0.0)
        self.assertLessEqual(modifier, 10.0)

        # Empty metadata
        self.assertEqual(0.0, engine._compute_risk_modifier([], []))


if __name__ == "__main__":
    unittest.main()
