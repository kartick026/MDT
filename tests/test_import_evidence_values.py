"""Missing repository facts remain missing instead of inferred numeric defaults."""
from services.repo_onboarding import RepoOnboarder
import pytest


def test_compose_missing_port_and_startup_order_do_not_invent_http_endpoint():
    services, edges, _ = RepoOnboarder()._parse_compose("""
services:
  web:
    build: web
    depends_on: [api]
  api:
    build: api
""")
    assert all(s["port"] is None and s["url"] is None for s in services)
    assert edges == [{"from": "web", "to": "api", "type": "startup", "endpoint": "", "evidence_kind": "compose_startup_order", "source_file": "docker-compose.yml"}]


def test_database_resources_and_named_application_services_are_not_discarded():
    nodes, edges, _ = RepoOnboarder()._parse_compose("""
services:
  postgres-adapter:
    image: company/postgres-adapter:latest
    depends_on: [store]
  store:
    image: postgres:17
""")
    assert {node["name"]:node["node_type"] for node in nodes} == {"postgres-adapter":"service", "store":"database"}
    assert edges[0]["to"] == "store" and edges[0]["type"] == "startup"


def test_failed_import_status_survives_reopening_directory(isolate_durable_store):
    store = isolate_durable_store
    store.create_project("qa", {"id":"qa-project", "name":"QA", "ready":False})
    ident = store.enqueue("qa", "qa-project", {"input":{"source":"import"}}, require_project=True)
    job = store.claim()
    assert job["id"] == ident
    assert store.finish(job, error="Insufficient architecture evidence")
    saved = store.get("project", "qa-project", "qa")
    assert saved["import_status"] == "failed" and saved["ready"] is False
    assert saved["import_error"] == "Insufficient architecture evidence"
    assert not store.finish(job, result={"kind":"import", "project":{**saved,"ready":True}})
    assert store.get("project", "qa-project", "qa")["import_status"] == "failed"


@pytest.mark.asyncio
async def test_manifest_declarations_prevent_duplicate_aliases_and_build_template_services():
    services, _, mappings = await RepoOnboarder()._infer_from_file_tree("owner", "repo", "sha",
        tree=["docker/Dockerfile", "docker/app.py", "src/payments/Dockerfile", "src/payments/main.py"],
        existing_services=[{"name":"payment-api", "discovery_kind":"compose"}],
        existing_mappings={"src/payments":"payment-api"})
    assert [service["name"] for service in services] == ["payment-api"]
    assert mappings == {"src/payments":"payment-api"}


@pytest.mark.asyncio
async def test_unassessed_graph_node_never_receives_fake_zero_or_ninety(monkeypatch):
    from unittest.mock import AsyncMock
    from api import services as routes
    from core.registry import RegistryManager
    monkeypatch.setattr(routes.graph,"get_all_services",AsyncMock(return_value=[{"name":"unknown","risk_score":99}]))
    with RegistryManager.use_snapshot({"services":[{"name":"unknown","is_broken":True}],"dependencies":[]},"qa-values"):
        result=await routes.get_service_graph()
        assert result["nodes"][0]["risk_score"] is None
        assert result["nodes"][0]["risk_level"] == "UNKNOWN"
        assert result["nodes"][0]["status"] == "unknown"
        client=AsyncMock()
        row=await routes._ping_service(client,{"name":"unknown"})
        client.get.assert_not_awaited()
        assert row["risk_score"] is None and row["status"] == "unobserved"


@pytest.mark.asyncio
async def test_service_list_preserves_missing_and_measured_zero_against_stale_graph(monkeypatch):
    from unittest.mock import AsyncMock
    from api import services as routes
    from core.registry import RegistryManager
    monkeypatch.setattr(routes.graph,"get_all_services",AsyncMock(return_value=[
        {"name":"missing","risk_score":99,"risk_level":"CRITICAL"},
        {"name":"zero","risk_score":99,"risk_level":"CRITICAL"}]))
    with RegistryManager.use_snapshot({"services":[{"name":"missing"},{"name":"zero","risk_score":0,"risk_level":"LOW"}],"dependencies":[]},"qa-values"):
        result=await routes.list_services()
        assert [row["risk_score"] for row in result["services"]] == [None,0]
        assert [row["risk_level"] for row in result["services"]] == ["UNKNOWN","LOW"]
