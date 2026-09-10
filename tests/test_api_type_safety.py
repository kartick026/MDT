"""
Tests for Type Safety, Pydantic Models, and API Contract Consistency (Phase 2)
"""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import app
from schemas.common import ErrorResponse, PaginatedResponse
from schemas.analysis import AnalysisResponse, HistoryResponse, SuggestedFix, ScoreBreakdown
from schemas.service import ServiceListResponse, ServiceGraphResponse, ServicePayload
from api.analysis import AnalysisRequest
from api import analysis as analysis_api
from api import services as services_api


@pytest.fixture
def client():
    return TestClient(app)


def test_analysis_request_validation():
    # Blank repo_url must fail validation
    with pytest.raises(ValidationError):
        AnalysisRequest(repo_url="   ", commit_sha="abc1234")

    # Blank commit_sha must fail validation
    with pytest.raises(ValidationError):
        AnalysisRequest(repo_url="https://github.com/kartick026/MDT", commit_sha="  ")

    # Valid request passes
    req = AnalysisRequest(repo_url="https://github.com/kartick026/MDT", commit_sha="main")
    assert req.repo_url == "https://github.com/kartick026/MDT"
    assert req.commit_sha == "main"


def test_common_schemas():
    err = ErrorResponse(detail="Not found", status_code=404)
    assert err.detail == "Not found"
    assert err.status_code == 404
    assert err.timestamp is not None

    paginated = PaginatedResponse[str](items=["svc-a", "svc-b"], total=2, limit=10, offset=0)
    assert len(paginated.items) == 2
    assert paginated.total == 2


def test_services_api_response_contract(client):
    response = client.get("/services/")
    assert response.status_code == 200
    data = response.json()
    validated = ServiceListResponse(**data)
    assert isinstance(validated.services, list)
    assert validated.total == len(validated.services)


def test_services_graph_api_response_contract(client):
    response = client.get("/services/graph")
    assert response.status_code == 200
    data = response.json()
    validated = ServiceGraphResponse(**data)
    assert isinstance(validated.nodes, list)
    assert isinstance(validated.edges, list)


def test_registry_add_service_contract(client):
    from core.auth import create_access_token
    token = create_access_token({"sub": "admin", "role": "admin"})
    payload = {
        "name": "test-microservice",
        "port": 8888,
        "url": "http://localhost:8888",
        "language": "python",
        "description": "Test microservice for type safety validation"
    }
    response = client.post(
        "/registry/services",
        json=payload,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["service"] == "test-microservice"


def test_analyze_empty_payload_rejected(client):
    response = client.post("/analysis/analyze", json={"repo_url": "", "commit_sha": ""})
    assert response.status_code == 422


def test_analysis_rejects_repository_that_does_not_own_active_architecture(client, monkeypatch):
    """A repository must never inherit another repository's service graph."""
    monkeypatch.setattr(
        analysis_api.RegistryManager,
        "get_project_context",
        lambda: {
            "repository_key": "github:owner/repository-a",
            "repo_url": "https://github.com/owner/repository-a",
            "branch": "main",
            "source": "repository",
        },
    )

    response = client.post(
        "/analysis/analyze",
        json={"repo_url": "https://github.com/owner/repository-b", "commit_sha": "main"},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "ACTIVE_PROJECT_MISMATCH"
    assert detail["active_repository"].endswith("repository-a")


def test_graph_uses_registry_snapshot_for_nodes_and_edges(client, monkeypatch):
    """A stale Neo4j node list cannot hide the order -> user dependency."""
    registry_services = [
        {"name": "user-service", "port": 8001, "risk_level": "LOW", "risk_score": 10},
        {"name": "order-service", "port": 8002, "risk_level": "MEDIUM", "risk_score": 30},
    ]
    monkeypatch.setattr(services_api.RegistryManager, "get_services", lambda: registry_services)
    monkeypatch.setattr(
        services_api.RegistryManager,
        "get_dependencies",
        lambda: [{"from": "order-service", "to": "user-service", "type": "http"}],
    )
    monkeypatch.setattr(services_api.RegistryManager, "get_connection_bugs", lambda: [])

    async def stale_graph_nodes():
        return [{"name": "user-service", "risk_score": 99, "risk_level": "CRITICAL"}]

    monkeypatch.setattr(services_api.graph, "get_all_services", stale_graph_nodes)
    response = client.get("/services/graph")

    assert response.status_code == 200
    body = response.json()
    assert {node["id"] for node in body["nodes"]} == {"user-service", "order-service"}
    assert body["edges"] == [{"from": "order-service", "to": "user-service", "type": "http", "has_bug": False}]
