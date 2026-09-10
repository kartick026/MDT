import pytest
import sys
from pathlib import Path
from starlette.testclient import TestClient

# Ensure backend is on sys.path
backend_dir = str(Path(__file__).parent.parent / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client):
    response = client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "healthy"


def test_services_list_endpoint(client):
    response = client.get("/services/")
    assert response.status_code == 200
    data = response.json()
    assert "services" in data
    assert isinstance(data["services"], list)
    assert len(data["services"]) > 0


def test_services_graph_endpoint(client):
    response = client.get("/services/graph")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)


def test_analysis_history_endpoint(client):
    response = client.get("/analysis/history")
    assert response.status_code == 200
    data = response.json()
    assert "analyses" in data
    assert isinstance(data["analyses"], list)
    assert "total" in data



def test_registry_dependencies_endpoint(client):
    response = client.get("/registry/dependencies")
    assert response.status_code == 200
    deps = response.json()
    assert isinstance(deps, list)


def test_registry_file_mappings_endpoint(client):
    response = client.get("/registry/file_mappings")
    assert response.status_code == 200
    mappings = response.json()
    assert isinstance(mappings, dict)


def test_invalid_service_creation_rejected(client):
    # Unauthenticated returns 401
    unauth_response = client.post("/registry/services", json={})
    assert unauth_response.status_code == 401

    # Authenticated but invalid payload (missing required name and port) returns 422
    from core.auth import create_access_token
    token = create_access_token({"sub": "admin", "role": "admin"})
    response = client.post(
        "/registry/services",
        json={},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 422
