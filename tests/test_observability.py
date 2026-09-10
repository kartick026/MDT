import pytest
import sys
import json
import logging
from pathlib import Path
from starlette.testclient import TestClient

# Ensure backend is on sys.path
backend_dir = str(Path(__file__).parent.parent / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import app
from core.middleware import JSONLogFormatter


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_request_id_and_latency_headers(client):
    """Verify X-Request-ID and X-Response-Time-MS headers are attached to responses."""
    response = client.get("/health/")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0

    assert "X-Response-Time-MS" in response.headers
    latency = float(response.headers["X-Response-Time-MS"])
    assert latency >= 0.0


def test_custom_request_id_propagation(client):
    """Verify client-supplied X-Request-ID is preserved in response headers."""
    custom_id = "test-req-uuid-12345"
    response = client.get("/health/", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_id


def test_detailed_health_observability(client):
    """Verify /health/detailed returns structured component and environment data."""
    response = client.get("/health/detailed")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "app" in data
    assert "version" in data["app"]
    assert "components" in data
    assert "details" in data["components"]
    assert "neo4j" in data["components"]["details"]
    assert "chroma" in data["components"]["details"]
    assert "llm" in data["components"]["details"]
    assert "github" in data["components"]["details"]


def test_json_log_formatter():
    """Verify JSONLogFormatter outputs valid JSON with expected structured fields."""
    formatter = JSONLogFormatter()
    record = logging.LogRecord(
        name="mdt.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=42,
        msg="Test structured log message",
        args=(),
        exc_info=None
    )
    record.request_id = "req-test-999"
    record.latency_ms = 12.34

    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "mdt.test"
    assert parsed["message"] == "Test structured log message"
    assert parsed["request_id"] == "req-test-999"
    assert parsed["latency_ms"] == 12.34
    assert "timestamp" in parsed
