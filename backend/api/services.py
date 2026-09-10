"""
Services API routes
Exposes service registry, health checks, and dependency queries.
All data is live — no hardcoded responses.
"""
import asyncio
import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter

from core.registry import RegistryManager
from services.dependency_graph import DependencyGraph
from services.smell_detector import SmellDetector
from schemas.service import ServiceListResponse, ServiceGraphResponse

router = APIRouter()
logger = logging.getLogger(__name__)

graph = DependencyGraph()
smell_detector = SmellDetector()


async def _ping_service(client: httpx.AsyncClient, svc: dict) -> dict:
    """
    Ping a single microservice /health endpoint and return its live status.
    Uses the Docker-internal URL (e.g. http://user-service:8001).
    Falls back gracefully if the service is unreachable.
    """
    name = svc["name"]
    port = svc.get("port", 0)
    # Build a display name from the service name
    display_name = svc.get("display_name") or (
        name.replace("-service", "")
            .replace("-", " ")
            .title() + " Service"
    )

    # Resolve dependencies dynamically from the registry
    deps = [
        d["to"]
        for d in RegistryManager.get_dependencies()
        if d["from"] == name
    ]

    base = {
        "name": name,
        "display_name": display_name,
        "port": port,
        "url": svc.get("url", ""),
        "description": svc.get("description", ""),
        "dependencies": deps,
        "api_count": svc.get("api_count") or 0,
        "endpoints": svc.get("endpoints") or [],
        "risk_level": (svc.get("risk_level") or "UNKNOWN").upper(),
        "risk_score": svc.get("risk_score") or 0,
        "is_external": svc.get("is_external", False),
    }

    # Ping candidate URLs (Docker internal networking, trailing slashes, root)
    url = (svc.get("url") or f"http://localhost:{port}").rstrip("/")
    candidate_urls = [f"{url}/health/", f"{url}/health", f"{url}/"]
    # Registry URLs use Docker DNS names.  When the backend is run directly
    # on a developer machine, use the published local port as a fallback.
    if "//" in url and not os.path.exists("/.dockerenv"):
        host = url.split("//", 1)[1].split(":", 1)[0]
        if host.endswith("-service"):
            candidate_urls.extend([
                f"http://localhost:{port}/health/",
                f"http://localhost:{port}/health",
            ])
    if ":5173" in url or port == 5173 or name in ["frontend", "web", "ui"]:
        candidate_urls.extend(["http://frontend:80/", "http://frontend:80/health"])

    async def probe(target: str):
        try:
            return await client.get(target, timeout=0.8, follow_redirects=True)
        except Exception:
            return None

    # Probe candidates in parallel.  This prevents a missing imported service
    # from multiplying the dashboard refresh time by every URL fallback.
    responses = await asyncio.gather(*(probe(target) for target in candidate_urls))
    last_resp = next((response for response in responses if response is not None), None)
    healthy = any(response is not None and response.status_code < 400 for response in responses)

    if healthy:
        base["status"] = "healthy"
        # Try to extract endpoint count from /openapi.json or health data
        try:
            openapi_resp = await client.get(f"{url}/openapi.json", timeout=1.5, follow_redirects=True)
            if openapi_resp.status_code == 200:
                paths = openapi_resp.json().get("paths", {})
                base["api_count"] = len(paths)
            elif last_resp and hasattr(last_resp, "json"):
                data = last_resp.json()
                if isinstance(data, dict) and "endpoints" in data:
                    base["api_count"] = len(data["endpoints"])
        except Exception:
            pass
    elif svc.get("is_external"):
        base["status"] = "imported"
    else:
        base["status"] = "offline"

    return base


@router.get("", response_model=ServiceListResponse, include_in_schema=False)
@router.get("/", response_model=ServiceListResponse, summary="List all registered services with live health")
async def list_services():
    """
    Return all services from the dependency graph enriched with live health status.
    Pings each service's /health endpoint concurrently.
    """
    reg_services = RegistryManager.get_services()
    try:
        graph_services = await graph.get_all_services()
        graph_map = {s["name"]: s for s in graph_services}
    except Exception:
        graph_map = {}

    services = []
    for s in (reg_services or list(graph_map.values())):
        merged = {**s}
        gm = graph_map.get(s.get("name", ""), {})

        # Prioritize service's own specific risk score and level from registry
        if s.get("risk_score") is not None and s.get("risk_score") > 0:
            merged["risk_score"] = s["risk_score"]
        elif gm.get("risk_score") is not None and gm["risk_score"] > 0:
            merged["risk_score"] = gm["risk_score"]

        if s.get("risk_level") and s.get("risk_level") != "UNKNOWN":
            merged["risk_level"] = s["risk_level"]
        elif gm.get("risk_level") and gm["risk_level"] != "UNKNOWN":
            merged["risk_level"] = gm["risk_level"]

        if s.get("api_count"):
            merged["api_count"] = s["api_count"]
        if s.get("endpoints"):
            merged["endpoints"] = s["endpoints"]
        if s.get("is_external"):
            merged["is_external"] = s["is_external"]

        services.append(merged)

    # Ping all services concurrently
    async with httpx.AsyncClient() as client:
        tasks = [_ping_service(client, svc) for svc in services]
        enriched = await asyncio.gather(*tasks)

    return {"services": list(enriched), "total": len(enriched)}


@router.get("/graph", response_model=ServiceGraphResponse, summary="Return service nodes and dependency edges for the graph UI")
async def get_service_graph():
    """
    Return one internally consistent topology snapshot.

    The persisted registry is authoritative for both nodes and edges.  Neo4j
    is an analysis store and may be temporarily stale while an import/reset is
    in progress; using it as the node source could make a valid registry edge
    (for example order-service -> user-service) disappear from the UI.
    """
    registry_services = RegistryManager.get_services()
    try:
        graph_services = await graph.get_all_services()
        graph_risk = {service.get("name"): service for service in graph_services}
    except Exception:
        graph_risk = {}

    nodes = []
    for svc in registry_services:
        name = svc.get("name", "")
        if not name:
            continue
        # Registry data wins.  Graph risk is only a fallback for older
        # registry entries that have not yet received a risk assessment.
        graph_data = graph_risk.get(name, {})
        risk_score = svc.get("risk_score")
        risk_level = svc.get("risk_level")
        nodes.append({
            "id": name,
            "label": name.replace("-service", "").replace("-", " ").title(),
            "port": svc.get("port", 0),
            "risk_level": (risk_level or graph_data.get("risk_level") or "UNKNOWN").upper(),
            "risk_score": risk_score if risk_score is not None else (graph_data.get("risk_score") or 0),
        })

    # The registry is the source of truth.  The old process-local list was
    # never updated by repository onboarding and lost data on restart.
    bugged_pairs = {
        (bug.get("source_service"), bug.get("target_service"))
        for bug in RegistryManager.get_connection_bugs()
        if bug.get("source_service") and bug.get("target_service")
    }

    node_ids = {node["id"] for node in nodes}
    edges = [
        {
            "from": d["from"],
            "to": d["to"],
            "type": d.get("type", "http"),
            "has_bug": (d["from"], d["to"]) in bugged_pairs
        }
        for d in RegistryManager.get_dependencies()
        if d.get("from") in node_ids and d.get("to") in node_ids
    ]

    return {"nodes": nodes, "edges": edges}


@router.get("/smells", summary="Detect architectural smells")
async def get_architectural_smells():
    """Run all heuristics and Cypher queries to detect architectural smells."""
    smells = await smell_detector.detect_all_smells()
    return {"smells": smells, "count": len(smells)}


@router.get("/{service_name}", summary="Health check a specific service")
async def get_service_health(service_name: str):
    """Ping a microservice's /health endpoint and return its status."""
    info = await graph.get_service_info(service_name)
    if not info:
        known_services = RegistryManager.get_services()
        known = next((s for s in known_services if s["name"] == service_name), None)
        if not known:
            return {
                "error": "Service not found",
                "available": [s["name"] for s in known_services],
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
