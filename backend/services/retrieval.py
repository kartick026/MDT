"""
ChromaDB Retrieval Service
Semantic search for code context
"""
import logging
from typing import List, Dict, Any
from core.database import get_chroma_client
from core.config import settings

logger = logging.getLogger(__name__)


class RetrievalEngine:
    """
    ChromaDB-based semantic retrieval for code context
    Used by HMDA to retrieve relevant similar changes
    """

    def __init__(self):
        self.client = get_chroma_client()
        self.collection_name = "mdt_code_context"

    async def initialize(self):
        """Initialize ChromaDB collection"""
        if not self.client:
            logger.warning("ChromaDB not connected, skipping init")
            return

        try:
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "MDT code context for semantic retrieval"}
            )
            logger.info("ChromaDB collection initialized")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")

    async def index_code(
        self,
        file_path: str,
        content: str,
        embedding: List[float],
        metadata: Dict[str, Any]
    ):
        """Index a code snippet for retrieval"""
        if not self.client:
            return

        try:
            self.collection.add(
                ids=[file_path],
                embeddings=[embedding],
                documents=[content],
                metadatas=[{"file_path": file_path, **metadata}]
            )
            logger.debug(f"Indexed: {file_path}")
        except Exception as e:
            logger.error(f"Failed to index code: {e}")

    async def retrieve_similar(
        self,
        changes: List,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Retrieve similar code contexts for given changes
        Used to augment LLM context for better explanations
        """
        if not self.client:
            return {"documents": [], "risk_modifier": 0}

        try:
            # Build query from change information
            query_parts = []
            for change in changes:
                file_path = getattr(change, 'file_path', str(change))
                query_parts.append(file_path)

            query_text = " ".join(query_parts)

            # Query ChromaDB (placeholder - would use actual embeddings)
            # In production, generate embeddings for the query
            results = self.collection.query(
                query_texts=[query_text],
                n_results=top_k
            )

            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]

            # Calculate risk modifier based on similarity
            risk_modifier = 0
            if documents:
                # Higher similarity = potentially higher risk (history of issues)
                risk_modifier = 5  # Could analyze metadata for actual risk

            return {
                "documents": documents,
                "metadatas": metadatas,
                "risk_modifier": risk_modifier
            }

        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            return {"documents": [], "risk_modifier": 0}

    async def get_similar_changes(self, file_path: str, service: str) -> List[Dict]:
        """Get historical changes similar to a file"""
        if not self.client:
            return []

        try:
            results = self.collection.query(
                query_texts=[file_path],
                where={"service": service},
                n_results=3
            )
            return results.get("metadatas", [[]])[0]
        except Exception as e:
            logger.error(f"Failed to get similar changes: {e}")
            return []