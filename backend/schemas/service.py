"""Service registry, health, and topology schemas"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any


class ServiceItem(BaseModel):
    """Detailed microservice metadata and health status"""
    name: str
    display_name: Optional[str] = None
    port: int = 0
    url: str = ""
    language: Optional[str] = "python"
    description: Optional[str] = ""
    dependencies: List[str] = []
    api_count: int = 0
    risk_level: str = "UNKNOWN"
    risk_score: float = 0.0
    status: str = "offline"
    is_broken: bool = False


class ServiceListResponse(BaseModel):
    """Response containing list of registered services"""
    services: List[ServiceItem]
    total: int


class GraphNode(BaseModel):
    """Service node for frontend dependency graph UI"""
    id: str
    label: str
    port: int = 0
    risk_level: str = "UNKNOWN"
    risk_score: float = 0.0
    is_broken: bool = False
    status: str = "healthy"


class GraphEdge(BaseModel):
    """Dependency edge between services"""
    from_svc: str = Field(..., alias="from")
    to_svc: str = Field(..., alias="to")
    type: str = "http"
    has_bug: bool = False

    model_config = ConfigDict(populate_by_name=True)


class ServiceGraphResponse(BaseModel):
    """Full dependency topology graph"""
    nodes: List[GraphNode]
    edges: List[Dict[str, Any]]


class ServicePayload(BaseModel):
    """Payload to register or update a service"""
    name: str
    port: int
    url: str
    language: str = "python"
    description: str = ""


class DependencyPayload(BaseModel):
    """Payload to register a dependency edge"""
    from_svc: str
    to_svc: str
    dep_type: str = "http"
    endpoint: str = ""


class FileMappingPayload(BaseModel):
    """Payload to register a directory prefix to service mapping"""
    prefix: str
    service_name: str


class ImportRepoRequest(BaseModel):
    """Payload to auto-discover and import microservices from a Git repository"""
    repo_url: str
    branch: Optional[str] = "main"


class StatusResponse(BaseModel):
    """Standard operation status response"""
    status: str = "success"
    message: Optional[str] = None
    service: Optional[str] = None
