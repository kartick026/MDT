"""Durable ownership, quotas and idempotency regressions from security review."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import time

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from core.config import settings
from core.store import Store, IdempotencyConflict, ProjectNotFound


@pytest.fixture
def store(tmp_path):
    return Store("sqlite:///" + str(tmp_path / "security.sqlite3"))


def test_record_write_cannot_overwrite_another_owner(store):
    store.put("project", "known-id", "alice", {"name": "Alice's project"})
    with pytest.raises(ValueError, match="another owner"):
        store.put("project", "known-id", "bob", {"name": "replaced"})
    assert store.get("project", "known-id", "alice") == {"name": "Alice's project"}
    assert store.get("project", "known-id", "bob") is None
    store.put("project", "known-id", "alice", {"name": "Updated by owner"})
    assert store.get("project", "known-id", "alice")["name"] == "Updated by owner"


def test_account_creation_is_insert_only_under_concurrent_requests(store):
    def create(marker):
        try:
            store.create_account("same-user", {"password_hash": marker, "role": "viewer"})
            return marker
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(create, ["hash-a", "hash-b", "hash-c", "hash-d"]))
    winners = [value for value in outcomes if value is not None]
    assert len(winners) == 1
    assert store.get("account", "same-user", "auth")["password_hash"] == winners[0]


def test_project_quota_is_atomic_across_concurrent_creates(store, monkeypatch):
    monkeypatch.setattr(settings, "MAX_PROJECTS_PER_USER", 2)
    def create(i):
        try:
            store.create_project("alice", {"id": f"project-{i}"})
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        created = list(pool.map(create, range(12)))
    assert sum(created) == 2
    assert len(store.list("project", "alice")) == 2


def test_deleting_project_does_not_reset_daily_usage_quota(store, monkeypatch):
    monkeypatch.setattr(settings, "MAX_JOBS_PER_DAY", 1)
    store.create_project("alice", {"id": "first"})
    job_id = store.enqueue("alice", "first", {"input": "first"})
    store.delete_project("first", "alice")
    assert store.job(job_id, "alice") is None
    store.create_project("alice", {"id": "second"})
    with pytest.raises(ValueError, match="quota"):
        store.enqueue("alice", "second", {"input": "second"})
    # Another user's independent quota is unaffected.
    assert store.enqueue("bob", "bob-project", {"input": "bob"})


def test_idempotency_returns_same_job_only_for_same_input(store):
    first = store.enqueue("alice", "p", {"input": "a"}, "alice-p-key", "fingerprint-a")
    assert store.enqueue("alice", "p", {"input": "a"}, "alice-p-key", "fingerprint-a") == first
    with pytest.raises(IdempotencyConflict):
        store.enqueue("alice", "p", {"input": "b"}, "alice-p-key", "fingerprint-b")


def test_idempotency_mismatch_is_http_409(store, monkeypatch):
    from api import projects
    monkeypatch.setattr(projects, "get_store", lambda: store)
    store.create_project("alice", {"id": "p", "ready": True, "snapshot_version": "v1"})
    user = SimpleNamespace(username="alice", role="analyst")
    first = projects.submit_analysis("p", projects.AnalysisInput(head_ref="first"), user, "same-key")
    assert first["status"] == "queued"
    with pytest.raises(HTTPException) as error:
        projects.submit_analysis("p", projects.AnalysisInput(head_ref="second"), user, "same-key")
    assert error.value.status_code == 409


def test_owner_cannot_read_or_cancel_other_users_job(store):
    ident = store.enqueue("alice", "p", {"private": "source"})
    assert store.job(ident, "bob") is None
    assert store.cancel(ident, "bob") is None
    assert store.job(ident, "alice")["status"] == "queued"


def test_owned_job_submission_requires_an_existing_owned_project(store):
    store.create_project("alice", {"id": "private"})
    with pytest.raises(ProjectNotFound):
        store.enqueue("bob", "private", {"source": "private"}, require_project=True)
    with pytest.raises(ProjectNotFound):
        store.enqueue("alice", "missing", {"source": "deleted"}, require_project=True)


def test_api_submission_racing_project_deletion_does_not_recreate_source(store, monkeypatch):
    from api import projects
    monkeypatch.setattr(projects, "get_store", lambda: store)
    store.create_project("alice", {"id": "p", "ready": True, "snapshot_version": "v1"})
    original_enqueue = store.enqueue
    def delete_before_enqueue(*args, **kwargs):
        store.delete_project("p", "alice")
        return original_enqueue(*args, **kwargs)
    monkeypatch.setattr(store, "enqueue", delete_before_enqueue)
    user = SimpleNamespace(username="alice", role="analyst")
    with pytest.raises(HTTPException) as error:
        projects.submit_analysis("p", projects.AnalysisInput(head_ref="HEAD"), user, None)
    assert error.value.status_code == 404
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM jobs WHERE owner='alice'").fetchone()["n"] == 0


def test_concurrent_delete_and_enqueue_leave_no_orphaned_job(store):
    store.create_project("alice", {"id": "p"})
    def submit():
        try:
            return store.enqueue("alice", "p", {"source": "private"}, require_project=True)
        except ProjectNotFound:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        submissions = pool.submit(submit)
        deletion = pool.submit(store.delete_project, "p", "alice")
        submissions.result()
        deletion.result()
    assert store.get("project", "p", "alice") is None
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM jobs WHERE owner='alice'").fetchone()["n"] == 0


def test_api_deletion_after_enqueue_returns_not_found_instead_of_server_error(store, monkeypatch):
    from api import projects
    monkeypatch.setattr(projects, "get_store", lambda: store)
    store.create_project("alice", {"id": "p", "ready": True, "snapshot_version": "v1"})
    original_enqueue = store.enqueue
    def enqueue_then_delete(*args, **kwargs):
        ident = original_enqueue(*args, **kwargs)
        store.delete_project("p", "alice")
        return ident
    monkeypatch.setattr(store, "enqueue", enqueue_then_delete)
    with pytest.raises(HTTPException) as error:
        projects.submit_analysis("p", projects.AnalysisInput(head_ref="HEAD"), SimpleNamespace(username="alice", role="analyst"), None)
    assert error.value.status_code == 404


def test_expired_lease_cannot_publish_after_job_is_reclaimed(store):
    ident = store.enqueue("alice", "p", {"input": "source"})
    old = store.claim()
    with store.connection(write=True) as db:
        db.execute("UPDATE jobs SET expires=? WHERE id=?", (time.time() - 10, ident))
    current = store.claim()
    assert current["lease"] != old["lease"]
    assert not store.finish(old, {"result": "stale"})
    assert store.finish(current, {"result": "current"})
    assert store.job(ident, "alice")["result"] == {"result": "current"}


def test_revocation_retention_uses_expiry_not_record_age(store):
    store.put("revoked", "long-session", "auth", {"expires": time.time() + 30 * 86400})
    store.put("revoked", "expired-session", "auth", {"expires": time.time() - 1})
    with store.connection(write=True) as db:
        db.execute("UPDATE records SET created=? WHERE kind='revoked' AND id='long-session'", (time.time() - 10 * 86400,))
    store.prune()
    assert store.get("revoked", "long-session", "auth") is not None
    assert store.get("revoked", "expired-session", "auth") is None


@pytest.mark.parametrize("payload", [
    {"source": "patch", "base_ref": "HEAD", "after_files": {"a.py": "new"}},
    {"source": "patch", "base_ref": "HEAD", "before_files": {"a.py": "old"}},
    {"source": "patch", "before_files": {}, "after_files": {"a.py": "new"}},
    {"source": "commit", "local_changes": []},
    {"source": "patch", "base_ref": "HEAD", "local_changes": [], "pull_request": 1},
])
def test_incomplete_or_ambiguous_patch_source_is_rejected(payload):
    from api.projects import AnalysisInput
    with pytest.raises(ValidationError):
        AnalysisInput(**payload)


def test_explicit_addition_and_deletion_source_sides_are_valid():
    from api.projects import AnalysisInput
    addition = AnalysisInput(source="patch", base_ref="HEAD", before_files={}, after_files={"a.py": "new"})
    deletion = AnalysisInput(source="patch", base_ref="HEAD", before_files={"a.py": "old"}, after_files={})
    assert addition.before_files == {}
    assert deletion.after_files == {}


def test_path_mapping_uses_longest_directory_boundary(monkeypatch):
    from services import dependency_graph
    monkeypatch.setattr(dependency_graph, "_get_file_service_map", lambda: {
        "": "root", "services/api": "api", "services/api/nested": "nested", "services/api-other": "other",
    })
    assert dependency_graph._infer_service_from_path("services/api/main.py") == "api"
    assert dependency_graph._infer_service_from_path("services/api/nested/main.py") == "nested"
    assert dependency_graph._infer_service_from_path("services/api-other/main.py") == "other"
    assert dependency_graph._infer_service_from_path("services/apiculture/main.py") == "root"
    assert dependency_graph._infer_service_from_path(r"services\api\nested\main.py") == "nested"
