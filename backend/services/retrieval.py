"""
ChromaDB Retrieval Service — Phase 6 (Week 7)
==============================================
Semantic search over code context using ChromaDB + OpenAI embeddings.

Two embedding strategies:
  1. OpenAI text-embedding-ada-002  — when OPENAI_API_KEY is set (best quality)
  2. TF-IDF cosine similarity       — pure-Python fallback, no extra deps

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

logger = logging.getLogger(__name__)

COLLECTION_NAME = "mdt_code_context"
CHUNK_SIZE = 50       # lines per chunk
CHUNK_OVERLAP = 10    # lines of overlap between chunks


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

async def _openai_embed(texts: List[str]) -> Optional[List[List[float]]]:
    """Generate embeddings via OpenAI API. Returns None on failure."""
    if not settings.OPENAI_API_KEY:
        return None
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
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
    Simple TF-IDF vectors as a fallback when OpenAI is unavailable.
    Produces sparse-ish float lists good enough for cosine similarity in ChromaDB.
    """
    def tokenize(text: str) -> List[str]:
        return re.findall(r"[a-zA-Z_]\w*", text.lower())

    # Build corpus vocabulary
    all_tokens = []
    token_lists = [tokenize(t) for t in texts]
    for tl in token_lists:
        all_tokens.extend(tl)
    if vocab is None:
        vocab = list(dict.fromkeys(all_tokens))  # preserve order, dedupe
    vocab = vocab[:512]                           # cap dimension at 512

    vocab_idx = {w: i for i, w in enumerate(vocab)}
    n_docs = len(texts)

    # IDF
    doc_freq: Counter = Counter()
    for tl in token_lists:
        for w in set(tl):
            if w in vocab_idx:
                doc_freq[w] += 1
    idf = {w: math.log((n_docs + 1) / (doc_freq.get(w, 0) + 1)) + 1
           for w in vocab}

    # TF-IDF per document
    vectors = []
    for tl in token_lists:
        tf: Counter = Counter(tl)
        total = max(len(tl), 1)
        vec = [0.0] * len(vocab)
        for w, idx in vocab_idx.items():
            if tf[w] > 0:
                vec[idx] = (tf[w] / total) * idf[w]
        # L2 normalise
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vectors.append([v / norm for v in vec])
    return vectors


async def _embed(texts: List[str]) -> List[List[float]]:
    """Try OpenAI, fall back to TF-IDF."""
    result = await _openai_embed(texts)
    if result is not None:
        return result
    return _tfidf_embed(texts)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _chunk_content(content: str, file_path: str) -> List[Dict[str, Any]]:
    """
    Split file content into overlapping line windows.
    Returns list of {chunk_id, text, start_line, end_line}.
    """
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

class RetrievalEngine:
    """
    ChromaDB-based semantic retrieval for MDT code context.
    Degrades gracefully when ChromaDB is not connected.
    """

    def __init__(self):
        self._collection = None

    def _get_collection(self):
        """Lazy-load the ChromaDB collection."""
        if self._collection is not None:
            return self._collection
        client = get_chroma_client()
        if client is None:
            return None
        try:
            self._collection = client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={
                    "description": "MDT code context for semantic retrieval",
                    "hnsw:space": "cosine",
                },
            )
            logger.info("ChromaDB collection ready: %s", COLLECTION_NAME)
        except Exception as exc:
            logger.warning("ChromaDB collection init failed: %s", exc)
        return self._collection

    # ------------------------------------------------------------------ #
    #  Indexing
    # ------------------------------------------------------------------ #

    async def index_change(
        self,
        file_path: str,
        content: str,
        service: str,
        change_type: str,
        language: str,
        functions: List[str],
        classes: List[str],
        risk_score: float = 0.0,
    ):
        """
        Chunk a file and index every chunk into ChromaDB.
        Called after each analysis so future queries benefit from history.
        """
        collection = self._get_collection()
        if collection is None or not content.strip():
            return

        chunks = _chunk_content(content, file_path)
        if not chunks:
            return

        texts = [c["text"] for c in chunks]
        try:
            embeddings = await _embed(texts)
        except Exception as exc:
            logger.warning("Embedding generation failed: %s", exc)
            return

        ids = [c["chunk_id"] for c in chunks]
        metadatas = [
            {
                "file_path":   file_path,
                "service":     service,
                "change_type": change_type,
                "language":    language,
                "functions":   ",".join(functions[:20]),
                "classes":     ",".join(classes[:10]),
                "risk_score":  risk_score,
                "start_line":  c["start_line"],
                "end_line":    c["end_line"],
            }
            for c in chunks
        ]

        try:
            await asyncio.to_thread(
                collection.upsert,
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            logger.debug("Indexed %d chunks for %s", len(chunks), file_path)
        except Exception as exc:
            logger.warning("ChromaDB upsert failed for %s: %s", file_path, exc)

    # ------------------------------------------------------------------ #
    #  Retrieval
    # ------------------------------------------------------------------ #

    async def retrieve_similar(
        self,
        changes: List,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """
        Given a list of ChangeInfo objects, return the most semantically
        similar historical code chunks from ChromaDB.

        Returns:
            {
              documents:     List[str]         — chunk texts
              metadatas:     List[Dict]         — chunk metadata
              risk_modifier: float              — 0-10 extra risk points
            }
        """
        collection = self._get_collection()
        if collection is None:
            return {"documents": [], "metadatas": [], "risk_modifier": 0}

        # Build query text from file paths + AST symbols
        query_parts: List[str] = []
        for change in changes:
            fp = getattr(change, 'file_path', str(change))
            query_parts.append(fp.replace("/", " ").replace("_", " "))
            ast_meta = getattr(change, 'ast_metadata', {})
            query_parts.extend(ast_meta.get('functions', [])[:5])
            query_parts.extend(ast_meta.get('classes', [])[:3])
        query_text = " ".join(query_parts) or "code change"

        try:
            # Generate query embedding
            query_embeddings = await _embed([query_text])

            results = await asyncio.to_thread(
                collection.query,
                query_embeddings=query_embeddings,
                n_results=min(top_k, max(1, collection.count())),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.warning("ChromaDB query failed: %s", exc)
            return {"documents": [], "metadatas": [], "risk_modifier": 0}

        documents  = results.get("documents",  [[]])[0]
        metadatas  = results.get("metadatas",  [[]])[0]
        distances  = results.get("distances",  [[]])[0]

        # risk_modifier = weighted average of past risk_scores for close matches
        risk_modifier = self._compute_risk_modifier(metadatas, distances)

        return {
            "documents":    documents,
            "metadatas":    metadatas,
            "risk_modifier": risk_modifier,
        }

    def _compute_risk_modifier(
        self,
        metadatas: List[Dict],
        distances: List[float],
    ) -> float:
        """
        Score 0–10 based on how risky similar past changes were.
        Closer distance (lower cosine distance) = higher weight.
        """
        if not metadatas:
            return 0.0

        total_weight = 0.0
        weighted_risk = 0.0
        for meta, dist in zip(metadatas, distances):
            # cosine distance 0 = identical, 2 = opposite
            similarity = max(0.0, 1.0 - dist)
            past_risk = float(meta.get("risk_score", 0))
            weight = similarity
            weighted_risk += past_risk * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        avg_past_risk = weighted_risk / total_weight
        # Scale: past risk of 100 → +10 modifier; past risk of 50 → +5
        return round(min(10.0, avg_past_risk / 10.0), 2)

    async def get_similar_changes(
        self, file_path: str, service: str, top_k: int = 3
    ) -> List[Dict]:
        """Get historical changes for a specific file + service combination."""
        collection = self._get_collection()
        if collection is None:
            return []
        try:
            query_embeddings = await _embed([file_path])
            results = await asyncio.to_thread(
                collection.query,
                query_embeddings=query_embeddings,
                where={"service": service},
                n_results=min(top_k, max(1, collection.count())),
                include=["metadatas"],
            )
            return results.get("metadatas", [[]])[0]
        except Exception as exc:
            logger.warning("get_similar_changes failed: %s", exc)
            return []

    async def collection_stats(self) -> Dict[str, Any]:
        """Return stats about the indexed collection."""
        collection = self._get_collection()
        if collection is None:
            return {"status": "unavailable", "count": 0}
        try:
            count = await asyncio.to_thread(collection.count)
            return {
                "status": "connected",
                "collection": COLLECTION_NAME,
                "count": count,
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc), "count": 0}
