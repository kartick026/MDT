from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional

from core.registry import RegistryManager
from core.auth import require_admin
from schemas.auth import UserOut
from services.dependency_graph import DependencyGraph
from services.repo_onboarding import RepoOnboarder
from schemas.service import (
    ServicePayload,
    DependencyPayload,
    FileMappingPayload,
    ImportRepoRequest,
    StatusResponse,
)

router = APIRouter()
graph = DependencyGraph()
onboarder = RepoOnboarder()

# In-memory store for detected connection bugs
_latest_connection_bugs: List[Dict[str, Any]] = []


@router.get("/services")
def get_services() -> List[Dict[str, Any]]:
    return RegistryManager.get_services()


@router.get("/context")
def get_project_context() -> Dict[str, Any]:
    """Expose the repository that owns the active graph and file mappings."""
    return RegistryManager.get_project_context()


@router.post("/services", response_model=StatusResponse)
async def add_service(payload: ServicePayload, current_user: UserOut = Depends(require_admin)):
    data = payload.model_dump()
    RegistryManager.add_service(data)
    await graph.add_service(payload.name, data)
    return StatusResponse(status="success", service=payload.name)


@router.get("/dependencies")
def get_dependencies() -> List[Dict[str, Any]]:
    return RegistryManager.get_dependencies()


@router.post("/dependencies", response_model=StatusResponse)
async def add_dependency(payload: DependencyPayload, current_user: UserOut = Depends(require_admin)):
    RegistryManager.add_dependency(
        payload.from_svc, payload.to_svc, payload.dep_type, payload.endpoint
    )
    await graph.add_dependency(
        payload.from_svc, payload.to_svc, payload.dep_type, payload.endpoint
    )
    return StatusResponse(status="success")


@router.get("/file_mappings")
def get_file_mappings() -> Dict[str, str]:
    return RegistryManager.get_file_mappings()


@router.post("/file_mappings", response_model=StatusResponse)
def add_file_mapping(payload: FileMappingPayload, current_user: UserOut = Depends(require_admin)):
    RegistryManager.add_file_mapping(payload.prefix, payload.service_name)
    return StatusResponse(status="success")


@router.post("/import-repo")
async def import_repo(payload: ImportRepoRequest, current_user: UserOut = Depends(require_admin)):
    """
    Auto-discover and ingest microservice architecture from a GitHub repo.
    Parses docker-compose.yml or folder tree, registers services and dependencies,
    and runs ConnectionValidator to detect broken API contracts.
    """
    try:
        result = await onboarder.import_from_repo(payload.repo_url, payload.branch or "main")
        RegistryManager.set_connection_bugs(result.get("connection_bugs", []))
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/connection-bugs")
def get_connection_bugs() -> Dict[str, Any]:
    """Return all currently detected broken connections and 404 endpoints."""
    bugs = RegistryManager.get_connection_bugs()
    return {"bugs": bugs, "count": len(bugs)}


@router.post("/clear", response_model=StatusResponse)
def clear_registry(current_user: UserOut = Depends(require_admin)):
    RegistryManager.clear()
    RegistryManager.set_connection_bugs([])
    return StatusResponse(status="success", message="Registry cleared.")


@router.post("/reset-default", response_model=StatusResponse)
async def reset_default_registry(current_user: UserOut = Depends(require_admin)):
    """Reset registry and Neo4j graph back to the local Docker fleet (ports 8001-8004)."""
    RegistryManager.set_connection_bugs([])
    RegistryManager.reset_to_default()
    try:
        await graph.clear_graph()
        defaults = RegistryManager.load()
        for svc in defaults.get("services", []):
            await graph.add_service(svc["name"], svc)
        for dep in defaults.get("dependencies", []):
            await graph.add_dependency(dep["from"], dep["to"], dep.get("type", "http"), dep.get("endpoint", ""))
        await graph.seed_demo_history(RegistryManager.get_local_demo_smell_history())
    except Exception:
        pass
    return StatusResponse(status="success", message="Restored local demo fleet (ports 8001-8004) with all ten detector scenarios.")
