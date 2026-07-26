"""
Services API routes
Exposes service registry, health checks, and dependency queries.
Dependencies are served from the Neo4j graph (with static fallback).
"""
import logging
from typing import Optional

import httpx
from fastapi import APIRouter

from services.dependency_graph import DependencyGraph, KNOWN_SERVICES

router = APIRouter()
logger = logging.getLogger(__name__)

graph = DependencyGraph()


@router.get("/", summary="List all registered services")
async def list_services():
    """Return all services known to the dependency graph."""
    services = await graph.get_all_services()
    return {"services": services, "total": len(services)}


@router.get("/{service_name}", summary="Health check a specific service")
async def get_service_health(service_name: str):
    """Ping a microservice's /health endpoint and return its status."""
    info = await graph.get_service_info(service_name)
    if not info:
        return {
            "error": "Service not found",
            "available": [s["name"] for s in KNOWN_SERVICES],
        }

    port = info.get("port")
    url = info.get("url", f"http://localhost:{port}")

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"http://localhost:{port}/health")
            return {
                "service": service_name,
                "status": "healthy" if resp.status_code == 200 else "unhealthy",
                "port": port,
                "url": url,
            }
    except Exception as exc:
        return {
            "service": service_name,
            "status": "unreachable",
            "error": str(exc),
            "port": port,
        }


@router.get("/{service_name}/dependencies",
            summary="Get dependency chain for a service")
async def get_service_dependencies(service_name: str, depth: int = 4):
    """
    Return the full dependency chain for a service from Neo4j.
    Falls back to the static dependency map when Neo4j is unavailable.
    """
    chain = await graph.get_dependency_chain(service_name, depth=depth)
    dep_depth = await graph.get_dependency_depth(service_name)
    return {
        "service": service_name,
        "dependency_depth": dep_depth,
        "dependencies": chain,
        "source": "neo4j" if graph.driver else "static_map",
    }


@router.get("/{service_name}/affected-by",
            summary="Which services are affected if this service changes")
async def get_affected_by(service_name: str):
    """
    Given a service, return all services that depend on it
    and would be impacted by a change to it.
    """
    # Synthesise a fake file path for the service to reuse graph logic
    fake_path = f"services/{service_name.replace('-', '_')}/main.py"
    affected = await graph.get_affected_services(fake_path)
    return {
        "service": service_name,
        "affected_services": affected,
        "count": len(affected),
    }
