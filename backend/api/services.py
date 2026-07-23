"""Services routes"""
from fastapi import APIRouter, Query
from typing import List, Optional
import httpx

from core.config import settings

router = APIRouter()

MICROSERVICE_PORT_MAP = {
    "user": 8001,
    "order": 8002,
    "payment": 8003,
    "notification": 8004
}


@router.get("/")
async def list_services():
    """List all available services"""
    return {
        "services": [
            {"name": "user", "url": f"http://localhost:{MICROSERVICE_PORT_MAP['user']}"},
            {"name": "order", "url": f"http://localhost:{MICROSERVICE_PORT_MAP['order']}"},
            {"name": "payment", "url": f"http://localhost:{MICROSERVICE_PORT_MAP['payment']}"},
            {"name": "notification", "url": f"http://localhost:{MICROSERVICE_PORT_MAP['notification']}"}
        ]
    }


@router.get("/{service_name}")
async def get_service_health(service_name: str):
    """Get health status of a specific service"""
    port = MICROSERVICE_PORT_MAP.get(service_name.lower())

    if not port:
        return {"error": "Service not found", "available": list(MICROSERVICE_PORT_MAP.keys())}

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"http://localhost:{port}/health")
            return {
                "service": service_name,
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "port": port
            }
    except Exception as e:
        return {
            "service": service_name,
            "status": "unreachable",
            "error": str(e),
            "port": port
        }


@router.get("/{service_name}/dependencies")
async def get_service_dependencies(service_name: str):
    """Get dependencies for a service"""
    # In production, query Neo4j for actual dependencies
    # For now, return mock data
    dependencies = {
        "user": [],
        "order": ["user"],
        "payment": ["order"],
        "notification": ["order", "payment"]
    }

    return {
        "service": service_name,
        "dependencies": dependencies.get(service_name.lower(), [])
    }