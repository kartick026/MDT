"""Security and durable lifecycle invariants of the shared web/extension API."""
import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import app
from core.auth import create_access_token, hash_password
from core.config import settings
from core.registry import RegistryManager
from core.store import Store
from api.projects import evaluate_job


def headers(name="admin", role="admin"):
    return {"Authorization": "Bearer " + create_access_token({"sub": name, "role": role})}


@pytest.fixture
def client():
    return TestClient(app)


def make_project(client, auth=None):
    response = client.post("/v1/projects", headers=auth or headers(), json={
        "name": "test", "repo_url": settings.DEMO_REPO_URL, "use_demo": True})
    assert response.status_code == 201, response.text
    return response.json()


def test_public_demo_and_protected_data(client):
    demo = client.get("/v1/demo")
    assert demo.status_code == 200
    assert demo.json()["evidence"]["mode"] == "illustrative_demo"
    assert len([s for s in demo.json()["snapshot"]["services"] if s["node_type"] == "service"]) == 4
    for path in ("/v1/projects", "/analysis/history", "/services/graph", "/registry/context"):
        assert client.get(path).status_code == 401
    assert client.post("/analysis/analyze", json={}).status_code == 401
    assert client.post("/webhook/simulate", json={}).status_code == 401


def test_owner_isolation_and_live_role_check(client, isolate_durable_store):
    store = isolate_durable_store
    store.put("account", "alice", "auth", {"role": "analyst", "is_active": True})
    store.put("account", "bob", "auth", {"role": "analyst", "is_active": True})
    alice, bob = headers("alice"), headers("bob")
    project = make_project(client, alice)
    assert client.get("/v1/projects", headers=bob).json()["projects"] == []
    for method in (client.get, client.delete):
        assert method("/v1/projects/" + project["id"], headers=bob).status_code == 404
    # A forged role claim cannot promote an existing viewer.
    store.put("account", "bob", "auth", {"role": "viewer", "is_active": True})
    assert client.post("/v1/projects", headers=bob, json={"name": "x", "repo_url": settings.DEMO_REPO_URL}).status_code == 403
    store.put("account", "alice", "auth", {"role": "analyst", "is_active": False})
    assert client.get("/v1/projects", headers=alice).status_code == 401


def test_logout_and_refresh_revoke_old_tokens(client):
    auth = headers()
    assert client.get("/auth/me", headers=auth).status_code == 200
    refreshed = client.post("/auth/refresh", headers=auth)
    assert refreshed.status_code == 200
    assert client.get("/auth/me", headers=auth).status_code == 401
    new_auth = {"Authorization": "Bearer " + refreshed.json()["access_token"]}
    assert client.post("/auth/logout", headers=new_auth).status_code == 204
    assert client.get("/auth/me", headers=new_auth).status_code == 401
    assert client.get("/auth/me", headers=headers("unknown")).status_code == 401


@pytest.mark.asyncio
async def test_patch_job_real_pipeline_persists_and_preview_is_immutable(client, isolate_durable_store):
    store = isolate_durable_store
    project, auth = make_project(client), headers()
    baseline_registry = RegistryManager.load()
    source = {"source": "patch", "base_ref": "a"*40,
              "before_files": {"services/user_service/main.py": "@app.get('/users')\ndef users():\n return []\n"},
              "after_files": {"services/user_service/main.py": "@app.get('/members')\ndef users():\n return []\n"}}
    submitted = client.post(f"/v1/projects/{project['id']}/analyses", json=source, headers={**auth, "Idempotency-Key": "same-request"})
    assert submitted.status_code == 202, submitted.text
    ident = submitted.json()["job_id"]
    again = client.post(f"/v1/projects/{project['id']}/analyses", json=source, headers={**auth, "Idempotency-Key": "same-request"})
    assert again.json()["job_id"] == ident
    job = store.claim()
    result = await evaluate_job(job)
    assert result["evidence"]["semantic_used"] is False
    assert result["risk_score"] > 0
    assert store.finish(job, result=result)
    reopened = Store(store.path)
    assert reopened.job(ident, "admin")["result"]["snapshot_version"] == result["snapshot_version"]
    with store.connection() as db:
        assert db.execute("SELECT payload FROM jobs WHERE id=?", (ident,)).fetchone()["payload"] == "{}"
    fetched = client.get(f"/v1/jobs/{ident}", headers=auth).json()
    assert "_snapshot" not in fetched["result"]
    preview = client.post(f"/v1/analyses/{ident}/previews", headers=auth, json={"edits": [], "snapshot_version": result["snapshot_version"]})
    assert preview.status_code == 200, preview.text
    assert RegistryManager.load() == baseline_registry
    stale = client.post(f"/v1/analyses/{ident}/previews", headers=auth, json={"edits": [], "snapshot_version": "stale"})
    assert stale.status_code == 409
    assert store.job(ident, "nobody") is None


def test_leases_restart_cancellation_and_fencing(isolate_durable_store):
    store = isolate_durable_store
    ident = store.enqueue("owner", "project", {"source": "immutable"})
    with ThreadPoolExecutor(2) as pool:
        claims = list(pool.map(lambda _: store.claim(), range(2)))
    assert sum(job is not None for job in claims) == 1
    old = next(job for job in claims if job)
    with store.connection(write=True) as db:
        db.execute("UPDATE jobs SET expires=? WHERE id=?", (time.time()-1, ident))
    new = Store(store.path).claim()
    assert new["lease"] != old["lease"]
    assert not store.finish(old, result={"risk_score": 100})
    store.cancel(ident, "owner")
    assert not store.finish(new, result={"risk_score": 0})
    assert store.job(ident, "owner")["status"] == "cancelled"
    assert store.job(ident, "owner")["result"] is None


def test_saved_analysis_exposes_its_own_scan_without_rewriting_history(client, isolate_durable_store):
    store = isolate_durable_store
    project = make_project(client)
    project = store.get("project", project["id"], "admin")
    captured = {"candidate_files": 161, "files_read": 100, "parsers": {"tree_sitter": 52},
                "source": "static_source", "warnings": ["source_file_limit_reached"]}
    extraction = {"status": "complete", "files_analyzed": 1}
    ident = store.enqueue("admin", project["id"], {})
    job = store.claim()
    saved = {"kind": "analysis", "coverage": extraction,
             "snapshot_version": "historical-scan", "_snapshot": {**project["snapshot"], "coverage": captured}}
    assert store.finish(job, saved)
    # A subsequent import must not make an old scan look complete.
    project["snapshot"]["coverage"] = {"candidate_files": 161, "files_read": 161}
    store.put("project", project["id"], "admin", project)
    response = client.get(f"/v1/jobs/{ident}", headers=headers())
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["topology_coverage"] == captured
    assert result["coverage"] == extraction
    assert "_snapshot" not in result
    assert "topology_coverage" not in store.job(ident, "admin")["result"]
    assert client.get(f"/v1/jobs/{ident}", headers=headers("unknown")).status_code == 401


def test_quota_delete_and_bounded_input(client, isolate_durable_store, monkeypatch):
    store = isolate_durable_store
    monkeypatch.setattr(settings, "MAX_ACTIVE_JOBS_PER_USER", 1)
    ident = store.enqueue("owner", "project", {})
    with pytest.raises(ValueError, match="quota"):
        store.enqueue("owner", "project", {})
    job = store.claim()
    store.delete_project("project", "owner")
    assert store.job(ident, "owner") is None
    assert not store.finish(job, result={})
    project = make_project(client)
    assert client.post(f"/v1/projects/{project['id']}/analyses", headers=headers(), json={"source": "patch", "patch": "+not full source"}).status_code == 422
    monkeypatch.setattr(settings, "MAX_REQUEST_BYTES", 16)
    assert client.post("/auth/login", content=b"a"*17).status_code == 413


def test_snapshot_context_does_not_touch_global_registry():
    baseline = RegistryManager.load()
    with RegistryManager.use_snapshot({"services": [{"name": "one"}]}, "one"):
        RegistryManager.save({"services": [{"name": "changed"}]})
        with RegistryManager.use_snapshot({"services": [{"name": "two"}]}, "two"):
            assert RegistryManager.get_services()[0]["name"] == "two"
        assert RegistryManager.get_services()[0]["name"] == "changed"
    assert RegistryManager.load() == baseline


def test_hosted_configuration_requires_durable_secure_setup():
    from core.config import Settings
    with pytest.raises(ValueError):
        Settings(_env_file=None, RUNTIME_PROFILE="hosted", AUTH_REQUIRED=False)
    with pytest.raises(ValueError):
        Settings(_env_file=None, RUNTIME_PROFILE="hosted", ALLOW_SELF_SIGNUP=False, ENABLE_DEFAULT_VIEWER=False, DATABASE_URL="sqlite:///ephemeral.db")


def test_password_byte_limit():
    with pytest.raises(ValueError, match="72"):
        hash_password("é" * 40)
