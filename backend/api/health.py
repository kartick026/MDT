"""Health check endpoints"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from core.auth import get_current_user_optional
from core.config import settings
from core.database import check_neo4j_health, check_chroma_health

router = APIRouter()
logger = logging.getLogger(__name__)


def storage_health():
    from core.store import get_store
    store = get_store()
    with store.connection() as db:
        db.execute('SELECT 1').fetchone()
    return {'status': 'healthy', 'connected': True,
            'engine': 'postgresql' if store.postgres else 'sqlite',
            'history_retention': 'indefinite' if settings.JOB_RETENTION_DAYS == 0 else f'{settings.JOB_RETENTION_DAYS} days'}


@router.get("", include_in_schema=False)
@router.get("/", summary="Basic health check")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT
    }


@router.get("/ready", summary="Durable storage readiness")
def readiness():
    try:
        storage = storage_health()
    except Exception:
        raise HTTPException(503, "Durable storage unavailable")
    return {"status": "ready", "profile": settings.RUNTIME_PROFILE, "storage": storage}


@router.get("/detailed", summary="Detailed component health")
async def detailed_health(user=Depends(get_current_user_optional)):
    """Check connectivity and readiness of all backend components."""

    # 1. Neo4j connectivity
    neo4j_info = check_neo4j_health() if settings.RUNTIME_PROFILE == "local" else {"status": "disabled", "connected": False}

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
        "status": "configured" if llm_configured else "fallback_mode",
        "availability": "not_probed",
        "project_analysis_mode": "deterministic",
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

    try:
        storage_info = storage_health()
    except Exception:
        storage_info = {'status': 'unhealthy', 'connected': False}
    required = [storage_info.get('connected')]
    if settings.RUNTIME_PROFILE == 'local':
        required.extend([neo4j_info.get('connected'), chroma_info.get('connected')])
    overall = "healthy" if all(required) else "degraded"

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
            "storage": storage_info['status'],
            "details": {
                "storage": storage_info,
                "neo4j": neo4j_info,
                "chroma": chroma_info,
                "llm": llm_info,
                "github": github_info
            }
        },
        "chroma_indexed_chunks": chroma_count,
    }
