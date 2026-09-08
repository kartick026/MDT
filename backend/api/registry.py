from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from core.registry import RegistryManager
from services.dependency_graph import DependencyGraph
from services.repo_onboarding import RepoOnboarder

router = APIRouter()
graph = DependencyGraph()
onboarder = RepoOnboarder()

# In-memory store for detected connection bugs
_latest_connection_bugs: List[Dict[str, Any]] = []

class ServicePayload(BaseModel):
    name: str
    port: int
    url: str
    language: str
    description: str

class DependencyPayload(BaseModel):
    from_svc: str
    to_svc: str
    dep_type: str = "http"
    endpoint: str = ""

class FileMappingPayload(BaseModel):
    prefix: str
    service_name: str

class ImportRepoRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = "main"

@router.get("/services")
def get_services():
    return RegistryManager.get_services()

@router.post("/services")
async def add_service(payload: ServicePayload):
    RegistryManager.add_service(payload.dict())
    await graph.add_service(payload.name, payload.dict())
    return {"status": "success", "service": payload.name}

@router.get("/dependencies")
def get_dependencies():
    return RegistryManager.get_dependencies()

@router.post("/dependencies")
async def add_dependency(payload: DependencyPayload):
    RegistryManager.add_dependency(
        payload.from_svc, payload.to_svc, payload.dep_type, payload.endpoint
    )
    await graph.add_dependency(
        payload.from_svc, payload.to_svc, payload.dep_type, payload.endpoint
    )
    return {"status": "success"}

@router.get("/file_mappings")
def get_file_mappings():
    return RegistryManager.get_file_mappings()

@router.post("/file_mappings")
def add_file_mapping(payload: FileMappingPayload):
    RegistryManager.add_file_mapping(payload.prefix, payload.service_name)
    return {"status": "success"}

@router.post("/import-repo")
async def import_repo(payload: ImportRepoRequest):
    """
    Auto-discover and ingest microservice architecture from a GitHub repo.
    Parses docker-compose.yml or folder tree, registers services and dependencies,
    and runs ConnectionValidator to detect broken API contracts.
    """
    global _latest_connection_bugs
    try:
        # Clear existing registry and graph to prevent mixing projects
        RegistryManager.clear()
        await graph.clear_graph()
        
        result = await onboarder.import_from_repo(payload.repo_url, payload.branch or "main")
        _latest_connection_bugs = result.get("connection_bugs", [])
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/connection-bugs")
def get_connection_bugs():
    """Return all currently detected broken connections and 404 endpoints."""
    return {"bugs": _latest_connection_bugs, "count": len(_latest_connection_bugs)}

@router.post("/clear")
def clear_registry():
    global _latest_connection_bugs
    RegistryManager.clear()
    _latest_connection_bugs = []
    return {"status": "success", "message": "Registry cleared."}
