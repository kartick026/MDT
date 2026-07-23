"""Health check endpoints"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def health_check():
    """Basic health check"""
    return {"status": "healthy"}


@router.get("/detailed")
async def detailed_health():
    """Detailed health check with component status"""
    return {
        "status": "healthy",
        "components": {
            "api": "healthy",
            "neo4j": "unknown",
            "chroma": "unknown"
        }
    }