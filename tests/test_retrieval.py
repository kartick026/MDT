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


class VersionedRetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_revisions_and_embedding_dimensions_do_not_overwrite_or_purge_history(self):
        from unittest.mock import patch, MagicMock, AsyncMock
        from services.retrieval import _tfidf_embed
        client = MagicMock()
        collections = {}
        def get_collection(**kwargs):
            collections.setdefault(kwargs["name"], MagicMock())
            return collections[kwargs["name"]]
        client.get_or_create_collection.side_effect = get_collection
        lexical = {"provider": "local", "model": "hashed-tokens-v1", "dimension": 256, "evidence_kind": "lexical"}
        semantic = {"provider": "test", "model": "learned-v2", "dimension": 3, "evidence_kind": "semantic"}
        embeddings = AsyncMock(side_effect=[(_tfidf_embed(["code"]), lexical), (_tfidf_embed(["code"]), lexical), ([[0.1, 0.2, 0.3]], semantic)])
        engine = RetrievalEngine()
        with patch("services.retrieval.get_chroma_client", return_value=client), patch("services.retrieval._embed_with_provenance", embeddings):
            for revision in ["a" * 40, "b" * 40, "c" * 40]:
                await engine.index_change("main.py", "def f(): pass", "api", "modified", "python", ["f"], [],
                    repository_key="github:o/r", project_id="project-a", commit_sha=revision, commit_timestamp=10)
        assert len(collections) == 2
        first_collection = next(iter(collections.values()))
        first_ids = first_collection.upsert.call_args_list[0].kwargs["ids"]
        second_ids = first_collection.upsert.call_args_list[1].kwargs["ids"]
        assert first_ids != second_ids
        client.delete_collection.assert_not_called()

    async def test_chronology_project_filters_and_lexical_zero_modifier(self):
        from unittest.mock import patch, MagicMock, AsyncMock
        from types import SimpleNamespace
        from services.retrieval import _tfidf_embed
        collection = MagicMock()
        collection.count.return_value = 5
        base = {"repository_key": "github:o/r", "project_id": "project-a", "risk_score": 100}
        collection.query.return_value = {
            "documents": [["past", "current", "future", "other project"]],
            "metadatas": [[{**base, "commit_sha": "a" * 40, "commit_timestamp": 5},
                           {**base, "commit_sha": "b" * 40, "commit_timestamp": 10},
                           {**base, "commit_sha": "c" * 40, "commit_timestamp": 20},
                           {**base, "project_id": "project-b", "commit_sha": "d" * 40, "commit_timestamp": 1}]],
            "distances": [[0, 0, 0, 0]]}
        lexical = {"provider": "local", "model": "hashed-tokens-v1", "dimension": 256, "evidence_kind": "lexical"}
        engine = RetrievalEngine()
        with patch("services.retrieval.get_chroma_client", return_value=MagicMock()), patch.object(engine, "_get_collection", return_value=collection), patch("services.retrieval._embed_with_provenance", AsyncMock(return_value=(_tfidf_embed(["query"]), lexical))):
            result = await engine.retrieve_similar([SimpleNamespace(file_path="main.py", ast_metadata={})],
                repository_key="github:o/r", project_id="project-a", target_commit_sha="b" * 40, before_timestamp=10)
        assert result["documents"] == ["past"]
        assert result["risk_modifier"] == 0 and result["evidence_kind"] == "lexical"
        where = collection.query.call_args.kwargs["where"]["$and"]
        assert {"project_id": "project-a"} in where
        assert {"commit_timestamp": {"$lt": 10}} in where

    async def test_disabled_retrieval_never_calls_embedding_provider(self):
        from unittest.mock import patch, AsyncMock
        with patch("services.retrieval.get_chroma_client", return_value=None), patch("services.retrieval._embed_with_provenance", AsyncMock()) as embed:
            engine = RetrievalEngine()
            await engine.index_change("main.py", "code", "api", "modified", "python", [], [],
                repository_key="github:o/r", project_id="project-a", commit_sha="a" * 40, commit_timestamp=1)
            await engine.retrieve_similar([], repository_key="github:o/r", project_id="project-a", target_commit_sha="b" * 40, before_timestamp=2)
            embed.assert_not_called()
