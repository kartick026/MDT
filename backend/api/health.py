"""Health check endpoints"""
import logging
from fastapi import APIRouter
from core.config import settings
from core.database import check_neo4j_health, check_chroma_health

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", include_in_schema=False)
@router.get("/", summary="Basic health check")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT
    }


@router.get("/detailed", summary="Detailed component health")
async def detailed_health():
    """Check connectivity and readiness of all backend components."""

    # 1. Neo4j connectivity
    neo4j_info = check_neo4j_health()

    # 2. ChromaDB connectivity & stats
    chroma_info = check_chroma_health()
    chroma_info["mode"] = settings.CHROMADB_MODE.lower()
    chroma_count = 0
    if chroma_info.get("connected"):
        try:
            from services.retrieval import RetrievalEngine
            stats = await RetrievalEngine().collection_stats()
            chroma_count = stats.get("count", 0)
        except Exception as exc:
            logger.debug("Could not retrieve Chroma stats: %s", exc)

    # 3. LLM readiness
    llm_configured = bool(settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.startswith("your_"))
    llm_info = {
        "status": "ready" if llm_configured else "fallback_mode",
        "model": settings.LLM_MODEL,
        "base_url": settings.LLM_BASE_URL or "default",
        "configured": llm_configured
    }

    # 4. GitHub integration
    github_configured = bool(settings.GITHUB_TOKEN or (settings.GITHUB_APP_ID and settings.GITHUB_APP_PRIVATE_KEY))
    github_info = {
        "status": "configured" if github_configured else "unauthenticated",
        "auth_type": "app" if settings.GITHUB_APP_ID else ("pat" if settings.GITHUB_TOKEN else "none")
    }

    overall = "healthy" if (neo4j_info.get("connected") and chroma_info.get("connected")) else "degraded"

    return {
        "status": overall,
        "app": {
            "name": settings.APP_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
            "log_level": settings.LOG_LEVEL,
            "log_format": settings.LOG_FORMAT
        },
        "components": {
            "api": "healthy",
            "neo4j": neo4j_info.get("status", "disconnected"),
            "chroma": chroma_info.get("status", "disconnected"),
            "details": {
                "neo4j": neo4j_info,
                "chroma": chroma_info,
                "llm": llm_info,
                "github": github_info
            }
        },
        "chroma_indexed_chunks": chroma_count,
    }
