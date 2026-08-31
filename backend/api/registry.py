from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from pydantic import BaseModel

from core.registry import RegistryManager
from services.dependency_graph import DependencyGraph

router = APIRouter()
graph = DependencyGraph()

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

@router.post("/clear")
def clear_registry():
    RegistryManager.clear()
    return {"status": "success", "message": "Registry cleared."}
