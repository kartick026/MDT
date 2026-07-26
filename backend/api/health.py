"""Health check endpoints"""
import logging
from fastapi import APIRouter
from core.database import get_neo4j_driver, get_chroma_client

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", summary="Basic health check")
async def health_check():
    return {"status": "healthy"}


@router.get("/detailed", summary="Detailed component health")
async def detailed_health():
    """Check connectivity of all backend components."""

    # Neo4j
    neo4j_status = "disconnected"
    try:
        driver = get_neo4j_driver()
        if driver:
            driver.verify_connectivity()
            neo4j_status = "connected"
    except Exception:
        neo4j_status = "unreachable"

    # ChromaDB
    chroma_status = "disconnected"
    chroma_count = 0
    try:
        client = get_chroma_client()
        if client:
            client.heartbeat()
            chroma_status = "connected"
            from services.retrieval import RetrievalEngine
            stats = await RetrievalEngine().collection_stats()
            chroma_count = stats.get("count", 0)
    except Exception:
        chroma_status = "unreachable"

    overall = "healthy" if neo4j_status == "connected" and chroma_status == "connected" \
        else "degraded"

    return {
        "status": overall,
        "components": {
            "api":     "healthy",
            "neo4j":   neo4j_status,
            "chroma":  chroma_status,
        },
        "chroma_indexed_chunks": chroma_count,
    }