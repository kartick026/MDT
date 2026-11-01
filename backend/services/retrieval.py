"""
ChromaDB Retrieval Service — Phase 6 (Week 7)
==============================================
Semantic search over code context using ChromaDB + OpenAI embeddings.

Two embedding strategies:
  1. OpenAI text-embedding-ada-002  — when OPENAI_API_KEY is set (best quality)
  2. Lexical hashed-token cosine similarity — explicitly non-semantic fallback

Indexing strategy:
  - Each changed file is chunked into ≤50-line windows with overlap
  - Each chunk stored with metadata: file_path, service, change_type,
    language, functions[], classes[], risk_score (from past analyses)

Retrieval strategy:
  - Query is built from changed file paths + AST symbols
  - Top-k most similar past chunks are returned
  - risk_modifier is the average past_risk_score of retrieved chunks,
    scaled to a 0–10 point boost
"""
import asyncio
import hashlib
import logging
import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from core.config import settings
from core.database import get_chroma_client
from core.registry import current_project_id

logger = logging.getLogger(__name__)

COLLECTION_NAME = getattr(settings, "CHROMADB_COLLECTION", "mdt_code_context")
CHUNK_SIZE = 50       # lines per chunk
CHUNK_OVERLAP = 10    # lines of overlap between chunks
FIXED_EMBED_DIM = 256 # Guaranteed fixed embedding dimension for fallback/hashing embeddings


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

async def _openai_embed(texts: List[str]) -> Optional[List[List[float]]]:
    """Generate embeddings via OpenAI API. Returns None on failure."""
    if (not settings.OPENAI_API_KEY or current_project_id()
            or getattr(settings, "RUNTIME_PROFILE", "local") == "hosted"):
        return None
    if settings.OPENAI_API_KEY.startswith("AIzaSy") and not settings.LLM_BASE_URL:
        return None
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.LLM_BASE_URL or None, timeout=4.0, max_retries=1)
        resp = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=texts,
        )
        return [item.embedding for item in resp.data]
    except Exception as exc:
        logger.warning("OpenAI embedding failed: %s", exc)
        return None


def _tfidf_embed(texts: List[str], vocab: Optional[List[str]] = None) -> List[List[float]]:
    """
    Fixed-dimension hashing vectorizer.
    Guarantees that every vector has EXACTLY FIXED_EMBED_DIM dimensions,
    preventing ChromaDB dimension mismatch errors across varying batch sizes and text inputs.
    """
    vectors = []
    for text in texts:
        tokens = re.findall(r"[a-zA-Z_]\w*", (text or "").lower())
        vec = [0.0] * FIXED_EMBED_DIM
        if tokens:
            tf = Counter(tokens)
            total = float(len(tokens))
            for token, count in tf.items():
                idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % FIXED_EMBED_DIM
                vec[idx] += count / total
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vec = [v / norm for v in vec]
        vectors.append(vec)
    return vectors


async def _embed(texts: List[str]) -> List[List[float]]:
    """Try OpenAI, fall back to fixed-dimension hashing embedding."""
    result = await _openai_embed(texts)
    if result is not None:
        return result
    return _tfidf_embed(texts)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _chunk_content(content: str, file_path: str) -> List[Dict[str, Any]]:
    lines = content.splitlines()
    chunks = []
    i = 0
    chunk_idx = 0
    while i < len(lines):
        end = min(i + CHUNK_SIZE, len(lines))
        text = "\n".join(lines[i:end])
        chunk_id = hashlib.md5(f"{file_path}:{i}".encode()).hexdigest()[:16]
        chunks.append({
            "chunk_id": chunk_id,
            "text": text,
            "start_line": i + 1,
            "end_line": end,
        })
        if end == len(lines):
            break
        i += CHUNK_SIZE - CHUNK_OVERLAP
        chunk_idx += 1
    return chunks


# ---------------------------------------------------------------------------
# RetrievalEngine
# ---------------------------------------------------------------------------

async def _embed_with_provenance(texts):
    vectors = await _openai_embed(texts)
    if vectors:
        dimensions = {len(vector) for vector in vectors}
        if len(vectors) != len(texts) or len(dimensions) != 1 or not all(
            math.isfinite(value) for vector in vectors for value in vector
        ):
            raise ValueError("Embedding provider returned invalid vectors.")
        provider = settings.LLM_BASE_URL or "https://api.openai.com/v1"
        return vectors, {"provider": provider, "model": settings.EMBEDDING_MODEL,
                         "dimension": len(vectors[0]), "evidence_kind": "semantic"}
    return _tfidf_embed(texts), {"provider": "local", "model": "hashed-tokens-v1",
                                "dimension": FIXED_EMBED_DIM, "evidence_kind": "lexical"}


class RetrievalEngine:
    """Versioned historical context. Incompatible embedding spaces never share collections."""

    def __init__(self):
        self._collections = {}

    def _get_collection(self, embedding=None):
        embedding = embedding or {"provider": "local", "model": "hashed-tokens-v1", "dimension": FIXED_EMBED_DIM}
        identity = f"{embedding['provider']}:{embedding['model']}:{embedding['dimension']}"
        name = f"{COLLECTION_NAME[:100]}-v2-{hashlib.sha256(identity.encode()).hexdigest()[:20]}"
        if name in self._collections:
            return self._collections[name]
        client = get_chroma_client()
        if client is None:
            return None
        try:
            collection = client.get_or_create_collection(name=name, embedding_function=None,
                metadata={"hnsw:space": "cosine", "provider": embedding["provider"],
                          "model": embedding["model"], "dimension": embedding["dimension"]})
            self._collections[name] = collection
            return collection
        except Exception as exc:
            logger.warning("Historical collection unavailable: %s", exc)
            return None

    async def index_change(self, file_path, content, service, change_type, language,
                           functions, classes, risk_score=0.0, repository_key="", *,
                           project_id="", commit_sha="", commit_timestamp=None):
        # Do not contaminate immutable history with anonymous, uncommitted or undated data.
        if not repository_key or not re.fullmatch(r"[0-9a-fA-F]{40}", commit_sha or "") or commit_timestamp is None or not content.strip():
            return
        if get_chroma_client() is None:
            return
        chunks = _chunk_content(content, file_path)
        try:
            vectors, embedding = await _embed_with_provenance([chunk["text"] for chunk in chunks])
            collection = self._get_collection(embedding)
            if collection is None:
                return
            scope = project_id or repository_key
            ids = [hashlib.sha256(f"{scope}:{repository_key}:{commit_sha}:{file_path}:{c['start_line']}:{embedding}:{c['text']}".encode()).hexdigest() for c in chunks]
            metadatas = [{"file_path": file_path, "service": service, "change_type": change_type,
                          "language": language, "functions": ",".join(functions[:20]),
                          "classes": ",".join(classes[:10]), "risk_score": float(risk_score),
                          "repository_key": repository_key, "project_id": scope,
                          "commit_sha": commit_sha, "commit_timestamp": int(commit_timestamp),
                          "start_line": c["start_line"], "end_line": c["end_line"], **embedding}
                         for c in chunks]
            await asyncio.to_thread(collection.upsert, ids=ids, embeddings=vectors,
                                    documents=[c["text"] for c in chunks], metadatas=metadatas)
        except Exception as exc:
            # Never purge history as an automatic recovery strategy.
            logger.warning("Historical indexing failed without changing existing records: %s", exc)

    def purge_collection(self) -> bool:
        """Legacy compatibility: global destructive collection resets are disabled."""
        return False

    async def retrieve_similar(self, changes, top_k=5, repository_key="", *, project_id="",
                               target_commit_sha="", before_timestamp=None):
        empty = {"documents": [], "metadatas": [], "risk_modifier": 0.0,
                 "evidence_kind": "unavailable", "semantic_scoring_enabled": False}
        if not repository_key or before_timestamp is None or not target_commit_sha:
            return {**empty, "reason": "immutable_revision_and_chronology_required"}
        if get_chroma_client() is None:
            return {**empty, "reason": "retrieval_disabled_or_unavailable"}
        parts = []
        for change in changes:
            parts.append(getattr(change, "file_path", ""))
            parts.extend(getattr(change, "ast_metadata", {}).get("functions", [])[:5])
        try:
            vectors, embedding = await _embed_with_provenance([" ".join(parts) or "code change"])
            collection = self._get_collection(embedding)
            if collection is None:
                return empty
            count = await asyncio.to_thread(collection.count)
            if not count:
                return {**empty, "evidence_kind": embedding["evidence_kind"]}
            scope = project_id or repository_key
            where = {"$and": [{"repository_key": repository_key}, {"project_id": scope},
                              {"commit_sha": {"$ne": target_commit_sha}},
                              {"commit_timestamp": {"$lt": int(before_timestamp)}}]}
            result = await asyncio.to_thread(collection.query, query_embeddings=vectors,
                n_results=min(max(1, top_k), count), where=where,
                include=["documents", "metadatas", "distances"])
            rows = zip((result.get("documents") or [[]])[0], (result.get("metadatas") or [[]])[0],
                       (result.get("distances") or [[]])[0])
            # Defense in depth for backends/adapters that accidentally ignore a filter.
            valid = [(d, m, distance) for d, m, distance in rows if m and
                     m.get("repository_key") == repository_key and m.get("project_id") == scope and
                     m.get("commit_sha") != target_commit_sha and
                     m.get("commit_timestamp", float("inf")) < before_timestamp]
            enabled = embedding["evidence_kind"] == "semantic" and getattr(settings, "SEMANTIC_SCORING_ENABLED", False)
            return {"documents": [row[0] for row in valid], "metadatas": [row[1] for row in valid],
                    "risk_modifier": self._compute_risk_modifier([row[1] for row in valid], [row[2] for row in valid]) if enabled else 0.0,
                    "evidence_kind": embedding["evidence_kind"], "embedding": embedding,
                    "semantic_scoring_enabled": bool(enabled)}
        except Exception as exc:
            logger.warning("Historical retrieval unavailable: %s", exc)
            return empty

    def _compute_risk_modifier(self, metadatas, distances):
        weight = total = 0.0
        for meta, distance in zip(metadatas, distances):
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            total += max(0.0, min(100.0, float(meta.get("risk_score", 0)))) * similarity
            weight += similarity
        return round(min(10.0, total / weight / 10.0), 3) if weight else 0.0

    async def get_similar_changes(self, file_path, service, top_k=3, **scope):
        # This compatibility endpoint must obey the same repository/project/time boundaries.
        from types import SimpleNamespace
        result = await self.retrieve_similar([SimpleNamespace(file_path=file_path, ast_metadata={})],
                                             top_k=top_k, **scope)
        return [m for m in result["metadatas"] if m.get("service") == service]

    async def collection_stats(self):
        if get_chroma_client() is None:
            return {"status": "unavailable", "count": 0}
        counts = []
        for collection in self._collections.values():
            try:
                counts.append(await asyncio.to_thread(collection.count))
            except Exception:
                pass
        return {"status": "connected", "count": sum(counts), "schema_version": 2,
                "scope": "collections_opened_by_this_engine", "collections": len(counts)}
