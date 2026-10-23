"""Owned history, immutable baselines and evidence-aware architecture comparison."""
import copy
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import app
from api.projects import evaluate_job
from core.auth import create_access_token
from core.registry import RegistryManager
from core.store import ProjectNotFound
from domain.architecture import GraphSnapshot
from domain.drift import compare_snapshots


def auth(owner="admin"):
    return {"Authorization": "Bearer " + create_access_token({"sub": owner, "role": "admin"})}


@pytest.fixture
def client():
    return TestClient(app)


def snapshot(revision="a" * 40):
    return {"services": [{"name": "api", "api_endpoints": [{"method": "GET", "path": "/items",
            "response_schema": {"type": "array"}}]}], "dependencies": [],
            "project": {"source": "repository", "revision": revision, "repo_url": "https://github.com/test/repo"},
            "coverage": {"files_read": 3, "warnings": []}}


def project(store, ident="p", owner="admin", name="API"):
    data = snapshot()
    value = {"id": ident, "name": name, "repo_url": "https://github.com/test/repo", "branch": "main",
             "ready": True, "snapshot": data, "snapshot_version": GraphSnapshot.from_data(data).version}
    store.create_project(owner, value)
    return value


def completed(store, value, owner="admin", data=None, partial=False):
    data = data or value["snapshot"]
    ident = store.enqueue(owner, value["id"], {"private_source": "must never appear in summaries"}, require_project=True)
    job = store.claim()
    assert job["id"] == ident
    result = {"kind": "analysis", "_snapshot": data, "snapshot_version": GraphSnapshot.from_data(data).version,
              "risk_score": 22, "architecture_smell_score": 12.3, "partial_results": partial,
              "commit_sha": data["project"]["revision"], "base_sha": "0" * 40}
    assert store.finish(job, result)
    return ident


def test_history_pagination_filters_literal_search_and_summary_privacy(client, isolate_durable_store):
    store = isolate_durable_store
    first = project(store, name="API 100%_ready!")
    second = project(store, "second", name="Other")
    ids = [completed(store, first), completed(store, second, partial=True), completed(store, first)]
    page = client.get("/v1/analyses?limit=2", headers=auth()).json()
    next_page = client.get("/v1/analyses?limit=2&offset=2", headers=auth()).json()
    assert page["total"] == next_page["total"] == 3
    assert len(page["analyses"]) == 2 and len(next_page["analyses"]) == 1
    assert {item["id"] for item in page["analyses"] + next_page["analyses"]} == set(ids)
    for item in page["analyses"]:
        assert not ({"result", "payload", "snapshot", "_snapshot"} & item.keys())
        assert item["risk_score"] == 22.0 and isinstance(item["partial_results"], bool)
    for query in ("100%_", "!", "API", "a" * 40):
        response = client.get("/v1/analyses", params={"q": query}, headers=auth()).json()
        assert response["total"] == (3 if query == "a" * 40 else 2)
    assert client.get("/v1/analyses", params={"q": "%' OR 1=1 --"}, headers=auth()).json()["total"] == 0
    assert client.get("/v1/analyses?status=partial", headers=auth()).json()["analyses"][0]["id"] == ids[1]
    assert client.get("/v1/analyses?project_id=p", headers=auth()).json()["total"] == 2
    for path in ("/v1/analyses?limit=0", "/v1/analyses?limit=101", "/v1/analyses?offset=-1", "/v1/analyses?status=unexpected"):
        assert client.get(path, headers=auth()).status_code == 422


def test_history_snapshot_and_baseline_endpoints_enforce_owner(client, isolate_durable_store):
    store = isolate_durable_store
    store.put("account", "bob", "auth", {"role": "analyst", "is_active": True})
    value = project(store)
    ident = completed(store, value)
    assert client.get("/v1/analyses", headers=auth("bob")).json()["analyses"] == []
    for path in ("/v1/analyses?project_id=p", f"/v1/analyses/{ident}/snapshot", "/v1/projects/p/snapshots", "/v1/projects/p/drift"):
        assert client.get(path, headers=auth("bob")).status_code == 404
        assert client.get(path).status_code == 401
    assert client.put("/v1/projects/p/baseline", headers=auth("bob"), json={"snapshot_version": value["snapshot_version"]}).status_code == 404


def test_initial_snapshot_baseline_and_same_capture_are_truthful(client, isolate_durable_store):
    value = project(isolate_durable_store)
    listed = client.get("/v1/projects/p/snapshots", headers=auth()).json()
    assert listed["baseline_version"] is None
    assert len(listed["snapshots"]) == 1
    assert listed["snapshots"][0]["revision"] == "a" * 40
    assert listed["snapshots"][0]["source_analysis_id"] is None
    assert client.get("/v1/projects/p/drift", headers=auth()).status_code == 409
    selected = client.put("/v1/projects/p/baseline", headers=auth(), json={"snapshot_version": value["snapshot_version"]})
    assert selected.status_code == 200 and selected.json()["baseline_version"] == value["snapshot_version"]
    drift = client.get("/v1/projects/p/drift", headers=auth()).json()
    assert drift["evidence"]["same_snapshot"] is True
    assert drift["evidence"]["revision_comparison"] is False
    assert any("import a revision" in warning for warning in drift["evidence"]["warnings"])
    assert drift["scores"]["delta"] == 0
    assert client.put("/v1/projects/p/baseline", headers=auth(), json={"snapshot_version": "uncaptured"}).status_code == 404


def test_seeded_demo_snapshot_discovery_and_legacy_baseline_compatibility(client, isolate_durable_store):
    from core.config import settings
    response = client.post("/v1/projects", headers=auth(), json={"name": "Demo", "repo_url": settings.DEMO_REPO_URL, "use_demo": True})
    assert response.status_code == 201
    ident = response.json()["id"]
    captures = client.get(f"/v1/projects/{ident}/snapshots", headers=auth()).json()["snapshots"]
    assert captures[0]["source"] == "illustrative_demo" and captures[0]["revision"] is None
    with isolate_durable_store.connection(write=True) as db:
        db.execute("DELETE FROM records WHERE kind='snapshot' AND project=?", (ident,))
    legacy = client.get(f"/v1/projects/{ident}/snapshots", headers=auth()).json()["snapshots"]
    assert legacy[0]["captured_at"] is None
    selected = client.put(f"/v1/projects/{ident}/baseline", headers=auth(), json={"snapshot_version": response.json()["snapshot_version"]})
    assert selected.status_code == 200
    drift = client.get(f"/v1/projects/{ident}/drift", headers=auth()).json()
    assert any("fixture data" in warning for warning in drift["evidence"]["warnings"])


def test_retention_preserves_pinned_baseline_and_current_capture(isolate_durable_store):
    store = isolate_durable_store
    value = project(store)
    pinned = snapshot("b" * 40)
    expired = snapshot("c" * 40)
    completed(store, value, data=pinned)
    completed(store, value, data=expired)
    pinned_version = GraphSnapshot.from_data(pinned).version
    store.set_project_baseline("p", "admin", pinned_version)
    with store.connection(write=True) as db:
        db.execute("UPDATE records SET created=? WHERE kind='snapshot'", (time.time() - 60 * 86400,))
    store.prune()
    assert {item["snapshot_version"] for item in store.snapshot_metadata("p", "admin")} == {value["snapshot_version"], pinned_version}


def test_archived_snapshot_is_immutable_and_separate_from_current_project(client, isolate_durable_store):
    store = isolate_durable_store
    value = project(store)
    ident = completed(store, value)
    newer = snapshot("b" * 40)
    newer["services"].append({"name": "worker"})
    value.update(snapshot=newer, snapshot_version=GraphSnapshot.from_data(newer).version)
    store.put("project", "p", "admin", value, "p")
    archived = client.get(f"/v1/analyses/{ident}/snapshot", headers=auth()).json()
    assert archived["snapshot"]["project"]["revision"] == "a" * 40
    assert archived["coverage"]["files_read"] == 3
    assert client.get(f"/v1/analyses/{ident}", headers=auth()).json()["result"].get("_snapshot") is None
    old_version = archived["snapshot_version"]
    existing = store.get("snapshot", "p:" + old_version, "admin")
    completed(store, value, data=archived["snapshot"])
    assert store.get("snapshot", "p:" + old_version, "admin") == existing


def test_contract_only_changes_affect_snapshot_version_but_source_lines_do_not():
    before = snapshot()
    after = copy.deepcopy(before)
    after["services"][0]["api_endpoints"][0]["response_schema"] = {"type": "object"}
    assert GraphSnapshot.from_data(before).version != GraphSnapshot.from_data(after).version
    relocated = copy.deepcopy(before)
    relocated["services"][0]["api_endpoints"][0].update(line=900, source_file="moved.py", coverage="static")
    assert GraphSnapshot.from_data(before).version == GraphSnapshot.from_data(relocated).version


def test_drift_reports_real_captures_contract_edits_edges_and_score_direction():
    before = snapshot()
    after = snapshot("b" * 40)
    after["services"][0]["api_endpoints"][0]["response_schema"] = {"type": "object"}
    after["services"].append({"name": "worker", "endpoints": ["/legacy"]})
    after["dependencies"] = [{"from": "api", "to": "worker"}, {"from": "worker", "to": "api"}]
    base = {"snapshot": before, "snapshot_version": GraphSnapshot.from_data(before).version}
    target = {"snapshot": after, "snapshot_version": GraphSnapshot.from_data(after).version}
    result = compare_snapshots(base, target)
    assert result["evidence"]["revision_comparison"] is True
    assert result["services"]["added"][0]["name"] == "worker"
    assert len(result["dependencies"]["added"]) == 2
    assert result["contracts"]["modified"][0]["path"] == "/items"
    assert result["contracts"]["added"][0]["method"] == "UNKNOWN"
    assert result["scores"]["direction"] == "worsened"
    assert result["scores"]["delta"] > 0
    assert any(finding["type"] == "Circular Dependency" for finding in result["findings"]["introduced"])


def test_baseline_and_finish_racing_deletion_cannot_recreate_project_records(isolate_durable_store):
    store = isolate_durable_store
    value = project(store)
    store.enqueue("admin", "p", {}, require_project=True)
    job = store.claim()
    result = {"_snapshot": value["snapshot"], "snapshot_version": value["snapshot_version"]}
    def baseline():
        try:
            store.set_project_baseline("p", "admin", value["snapshot_version"])
        except ProjectNotFound:
            pass
    with ThreadPoolExecutor(max_workers=3) as pool:
        operations = [pool.submit(baseline), pool.submit(store.finish, job, result), pool.submit(store.delete_project, "p", "admin")]
        for operation in operations:
            operation.result()
    assert store.get("project", "p", "admin") is None
    assert store.get("baseline", "p", "admin") is None
    assert store.snapshot_metadata("p", "admin") == []
    assert store.list_jobs("admin")["total"] == 0


@pytest.mark.asyncio
async def test_reimport_uses_requested_revision_and_persists_resolved_capture(monkeypatch, isolate_durable_store):
    from services.repo_onboarding import RepoOnboarder
    store = isolate_durable_store
    value = project(store)
    requested = []
    async def fake_import(self, repo, ref):
        requested.append(ref)
        RegistryManager.save(snapshot("b" * 40))
        return {"status": "success", "revision": "b" * 40, "coverage": {"warnings": []}}
    monkeypatch.setattr(RepoOnboarder, "import_from_repo", fake_import)
    ident = store.enqueue("admin", "p", {"project": value, "input": {"source": "import", "head_ref": "release-v2"}}, require_project=True)
    job = store.claim()
    result = await evaluate_job(job)
    assert requested == ["release-v2"]
    assert result["commit_sha"] == "b" * 40
    assert store.finish(job, result)
    assert store.get("project", "p", "admin")["snapshot"]["project"]["revision"] == "b" * 40
    metadata = store.snapshot_metadata("p", "admin")
    assert len(metadata) == 2
    assert metadata[0]["source_analysis_id"] == ident
