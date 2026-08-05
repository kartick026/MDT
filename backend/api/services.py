"""
Services API routes
Exposes service registry, health checks, and dependency queries.
All data is live — no hardcoded responses.
"""
import asyncio
import logging
from typing import Optional

import httpx
from fastapi import APIRouter

from services.dependency_graph import DependencyGraph, KNOWN_SERVICES, KNOWN_DEPENDENCIES

router = APIRouter()
logger = logging.getLogger(__name__)

graph = DependencyGraph()


async def _ping_service(client: httpx.AsyncClient, svc: dict) -> dict:
    """
    Ping a single microservice /health endpoint and return its live status.
    Uses the Docker-internal URL (e.g. http://user-service:8001).
    Falls back gracefully if the service is unreachable.
    """
    name = svc["name"]
    port = svc.get("port", 0)
    # Build a display name from the service name
    display_name = (
        name.replace("-service", "")
            .replace("-", " ")
            .title() + " Service"
    )

    # Attempt to resolve dependencies from the static map
    deps = [
        d["to"]
        for d in KNOWN_DEPENDENCIES
        if d["from"] == name
    ]

    base = {
        "name": name,
        "display_name": display_name,
        "port": port,
        "url": svc.get("url", ""),
        "description": svc.get("description", ""),
        "dependencies": deps,
        "api_count": 0,
        "risk_level": "UNKNOWN",
        "risk_score": 0,
    }

    # Ping the internal Docker URL
    url = svc.get("url") or f"http://localhost:{port}"
    try:
        resp = await client.get(f"{url}/health", timeout=2.0)
        if resp.status_code == 200:
            base["status"] = "healthy"
        else:
            base["status"] = "unhealthy"
        # Try to extract more info if the health endpoint is rich
        try:
            data = resp.json()
            if "endpoints" in data:
                base["api_count"] = len(data["endpoints"])
        except Exception:
            pass
    except Exception as exc:
        base["status"] = "offline"
        logger.debug("Service %s unreachable: %s", name, exc)

    return base


@router.get("/", summary="List all registered services with live health")
async def list_services():
    """
    Return all services from the dependency graph enriched with live health status.
    Pings each service's /health endpoint concurrently.
    """
    # Get the service list from Neo4j (falls back to KNOWN_SERVICES if Neo4j is down)
    raw_services = await graph.get_all_services()

    # Merge with KNOWN_SERVICES to ensure we always have URL/port info
    known_map = {s["name"]: s for s in KNOWN_SERVICES}
    merged = []
    for svc in raw_services:
        known = known_map.get(svc.get("name", ""), {})
        merged.append({**known, **svc})

    # Ping all services concurrently
    async with httpx.AsyncClient() as client:
        tasks = [_ping_service(client, svc) for svc in merged]
        enriched = await asyncio.gather(*tasks)

    return {"services": list(enriched), "total": len(enriched)}


@router.get("/graph", summary="Return service nodes and dependency edges for the graph UI")
async def get_service_graph():
    """
    Returns the full dependency graph as nodes + edges.
    Nodes come from Neo4j (or the static seed); edges come from KNOWN_DEPENDENCIES.
    """
    raw_services = await graph.get_all_services()
    known_map = {s["name"]: s for s in KNOWN_SERVICES}

    nodes = []
    for svc in raw_services:
        known = known_map.get(svc.get("name", ""), {})
        merged = {**known, **svc}
        name = merged.get("name", "")
        nodes.append({
            "id": name,
            "label": name.replace("-service", "").replace("-", " ").title(),
            "port": merged.get("port", 0),
            "risk_level": merged.get("risk_level", "UNKNOWN"),
            "risk_score": merged.get("risk_score", 0),
        })

    edges = [
        {"from": d["from"], "to": d["to"], "type": d.get("type", "http")}
        for d in KNOWN_DEPENDENCIES
    ]

    return {"nodes": nodes, "edges": edges}


@router.get("/{service_name}", summary="Health check a specific service")
async def get_service_health(service_name: str):
    """Ping a microservice's /health endpoint and return its status."""
    info = await graph.get_service_info(service_name)
    if not info:
        known = next((s for s in KNOWN_SERVICES if s["name"] == service_name), None)
        if not known:
            return {
                "error": "Service not found",
                "available": [s["name"] for s in KNOWN_SERVICES],
            }
        info = known

    port = info.get("port")
    url = info.get("url", f"http://localhost:{port}")

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{url}/health")
            return {
                "service": service_name,
                "status": "healthy" if resp.status_code == 200 else "unhealthy",
                "port": port,
                "url": url,
            }
    except Exception as exc:
        return {
            "service": service_name,
            "status": "offline",
            "error": str(exc),
            "port": port,
        }


@router.get("/{service_name}/dependencies",
            summary="Get dependency chain for a service")
async def get_service_dependencies(service_name: str, depth: int = 4):
    """Return the full dependency chain for a service from Neo4j."""
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
    """Given a service, return all services that depend on it."""
    fake_path = f"services/{service_name.replace('-', '_')}/main.py"
    affected = await graph.get_affected_services(fake_path)
    return {
        "service": service_name,
        "affected_services": affected,
        "count": len(affected),
    }
