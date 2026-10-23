"""Opt-in PostgreSQL persistence/concurrency tests.

Run with TEST_DATABASE_URL=postgresql://... python -m pytest -q
tests/test_store_postgres.py. The database role must be allowed to create schemas.
Each test creates a random schema and uses a search_path containing only that
schema. This is essential because claim/prune intentionally scan the job queue.
Cleanup drops only the schema created by that fixture, never shared tables.
The connection URL and credentials are never printed by this module.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import os
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import uuid

import pytest

from core.config import settings
from core.store import IdempotencyConflict, Store


pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL to opt in to PostgreSQL integration tests",
)


@dataclass
class PostgresCase:
    store: Store
    owner: str
    other: str
    project: str


@pytest.fixture
def pg_case(monkeypatch):
    psycopg = pytest.importorskip("psycopg", reason="Install psycopg[binary] for PostgreSQL tests")
    from psycopg import sql

    url = os.environ["TEST_DATABASE_URL"]
    parts = urlsplit(url)
    if parts.scheme not in {"postgres", "postgresql"}:
        pytest.fail("TEST_DATABASE_URL must be a PostgreSQL URL", pytrace=False)
    namespace = "mdt_test_" + uuid.uuid4().hex
    # Excluding public prevents accidental reads or mutations of real queue data.
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "options"]
    query.append(("options", "-csearch_path=" + namespace))
    isolated_url = urlunsplit(parts._replace(query=urlencode(query)))
    created = False
    try:
        with psycopg.connect(url, connect_timeout=10) as db:
            db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(namespace)))
        created = True
        monkeypatch.setattr(settings, "MAX_PROJECTS_PER_USER", 10)
        monkeypatch.setattr(settings, "MAX_ACTIVE_JOBS_PER_USER", 10)
        monkeypatch.setattr(settings, "MAX_JOBS_PER_DAY", 100)
        store = Store(isolated_url)
        with store.connection() as db:
            row = db.execute("SELECT current_schema() AS name").fetchone()
            assert row["name"] == namespace
        yield PostgresCase(store, namespace + "_owner", namespace + "_other", namespace + "_project")
    finally:
        if created:
            # The identifier is generated here, never read from input or the DB.
            assert namespace.startswith("mdt_test_") and len(namespace) == 41
            with psycopg.connect(url, connect_timeout=10) as db:
                db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(namespace)))


def test_postgres_reopen_owner_isolation_and_transaction_rollback(pg_case):
    s, owner, other, project = pg_case.store, pg_case.owner, pg_case.other, pg_case.project
    s.create_project(owner, {"id": project, "name": "Initial"})
    s.put("analysis", "analysis-1", owner, {"question": "Does '?' survive parameters?"}, project)
    reopened = Store(s.url)
    assert reopened.get("project", project, owner)["name"] == "Initial"
    assert reopened.list("analysis", owner, project)[0]["question"] == "Does '?' survive parameters?"
    assert reopened.get("project", project, other) is None
    with pytest.raises(ValueError, match="another owner"):
        reopened.put("project", project, other, {"name": "Overwritten"})
    assert s.get("project", project, owner)["name"] == "Initial"
    with pytest.raises(RuntimeError):
        with s.connection(write=True) as db:
            db.execute("DELETE FROM records WHERE owner=?", (owner,))
            raise RuntimeError("roll back test transaction")
    assert s.get("project", project, owner) is not None
    with s.connection() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM schema_versions").fetchone()["n"] == 1


def test_postgres_concurrent_account_and_project_creation(pg_case, monkeypatch):
    s, owner = pg_case.store, pg_case.owner
    monkeypatch.setattr(settings, "MAX_PROJECTS_PER_USER", 2)

    def account(i):
        try:
            s.create_account(owner, {"password_hash": "test-hash-" + str(i)})
            return i
        except ValueError:
            return None

    def project(i):
        try:
            s.create_project(owner, {"id": pg_case.project + str(i)})
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=6) as pool:
        winners = [x for x in pool.map(account, range(8)) if x is not None]
        projects = list(pool.map(project, range(8)))
    assert len(winners) == 1
    assert s.get("account", owner, "auth")["password_hash"] == "test-hash-" + str(winners[0])
    assert sum(projects) == 2
    assert len(s.list("project", owner)) == 2


def test_postgres_concurrent_enqueue_idempotency_and_quota(pg_case, monkeypatch):
    s, owner, project = pg_case.store, pg_case.owner, pg_case.project
    monkeypatch.setattr(settings, "MAX_ACTIVE_JOBS_PER_USER", 2)
    dedupe = owner + "_same-input"
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = list(pool.map(lambda _: s.enqueue(owner, project, {"source": "same"}, dedupe, "fingerprint"), range(8)))
    assert len(set(jobs)) == 1
    with pytest.raises(IdempotencyConflict):
        s.enqueue(owner, project, {"source": "different"}, dedupe, "different-fingerprint")

    def enqueue(i):
        try:
            return s.enqueue(owner, project, {"source": i})
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        added = [x for x in pool.map(enqueue, range(8)) if x]
    assert len(added) == 1
    assert len(s.list("usage", owner)) == 2
    assert s.enqueue(pg_case.other, project, {"source": "separate quota"})


def test_postgres_skip_locked_claims_and_terminal_source_erasure(pg_case):
    s, owner, project = pg_case.store, pg_case.owner, pg_case.project
    first = s.enqueue(owner, project, {"source": "private source one"})
    second = s.enqueue(owner, project, {"source": "private source two"})
    with s.connection(write=True) as locked:
        locked.execute("SELECT id FROM jobs WHERE id=? FOR UPDATE", (first,)).fetchone()
        with ThreadPoolExecutor(max_workers=1) as pool:
            claimed_second = pool.submit(s.claim).result(timeout=15)
        assert claimed_second["id"] == second
    claimed_first = s.claim()
    assert claimed_first["id"] == first
    assert s.claim() is None
    assert s.heartbeat(claimed_first)
    assert s.finish(claimed_second, {"partial_results": True, "risk_score": 10})
    assert s.finish(claimed_first, {"risk_score": 20})
    assert s.job(second, owner)["status"] == "partial"
    assert s.job(first, owner)["status"] == "succeeded"
    assert s.job(first, pg_case.other) is None
    assert "payload" not in s.job(first, owner)
    assert "lease" not in s.job(first, owner)
    with s.connection() as db:
        rows = db.execute("SELECT payload,lease,expires FROM jobs").fetchall()
    assert all(row["payload"] == "{}" and row["lease"] is None and row["expires"] is None for row in rows)


def test_postgres_restart_fences_stale_and_cancelled_imports(pg_case):
    s, owner, project = pg_case.store, pg_case.owner, pg_case.project
    s.create_project(owner, {"id": project, "ready": False})
    ident = s.enqueue(owner, project, {"source": "import"})
    old = s.claim()
    with s.connection(write=True) as db:
        db.execute("UPDATE jobs SET expires=? WHERE id=?", (time.time() - 10, ident))
    reopened = Store(s.url)
    current = reopened.claim()
    assert current["id"] == ident and current["lease"] != old["lease"]
    result = {"kind": "import", "project": {"id": project, "ready": True}}
    assert not s.heartbeat(old)
    assert not s.finish(old, result)
    assert s.get("project", project, owner)["ready"] is False
    assert reopened.cancel(ident, pg_case.other) is None
    assert reopened.finish(current, result)
    assert s.get("project", project, owner)["ready"] is True

    ident = s.enqueue(owner, project, {"source": "cancelled import"})
    cancelled = s.claim()
    s.cancel(ident, owner)
    assert not s.finish(cancelled, {"kind": "import", "project": {"id": project, "ready": False}})
    assert s.get("project", project, owner)["ready"] is True
    assert s.job(ident, owner)["status"] == "cancelled"


def test_postgres_exhausted_retries_and_retention(pg_case, monkeypatch):
    s, owner, project = pg_case.store, pg_case.owner, pg_case.project
    ident = s.enqueue(owner, project, {"source": "interrupted"})
    for _ in range(3):
        assert s.claim()["id"] == ident
        with s.connection(write=True) as db:
            db.execute("UPDATE jobs SET expires=? WHERE id=?", (time.time() - 10, ident))
    assert s.claim() is None
    assert s.job(ident, owner)["status"] == "failed"
    with s.connection() as db:
        assert db.execute("SELECT payload FROM jobs WHERE id=?", (ident,)).fetchone()["payload"] == "{}"
    monkeypatch.setattr(settings, "JOB_RETENTION_DAYS", 1)
    s.put("revoked", owner + "_expired", "auth", {"expires": time.time() - 1})
    s.put("revoked", owner + "_valid", "auth", {"expires": time.time() + 100})
    with s.connection(write=True) as db:
        db.execute("UPDATE jobs SET created=? WHERE id=?", (time.time() - 2 * 86400, ident))
    s.prune()
    assert s.job(ident, owner) is None
    assert s.get("revoked", owner + "_expired", "auth") is None
    assert s.get("revoked", owner + "_valid", "auth") is not None


def test_postgres_project_delete_keeps_daily_quota_and_other_owner(pg_case, monkeypatch):
    s, owner, project = pg_case.store, pg_case.owner, pg_case.project
    monkeypatch.setattr(settings, "MAX_JOBS_PER_DAY", 1)
    s.create_project(owner, {"id": project})
    s.put("analysis", "owned-analysis", owner, {"risk_score": 1}, project)
    own_job = s.enqueue(owner, project, {"source": "owned"})
    other_job = s.enqueue(pg_case.other, project, {"source": "unrelated owner"})
    s.delete_project(project, owner)
    assert s.get("project", project, owner) is None
    assert s.list("analysis", owner, project) == []
    assert s.job(own_job, owner) is None
    assert s.job(other_job, pg_case.other)["status"] == "queued"
    with pytest.raises(ValueError, match="quota"):
        s.enqueue(owner, project + "_next", {"source": "daily quota remains"})


def test_postgres_history_projection_search_and_snapshot_baseline(pg_case):
    from domain.architecture import GraphSnapshot
    s, owner, project = pg_case.store, pg_case.owner, pg_case.project
    snapshot = {"services": [{"name": "api"}], "dependencies": [],
                "project": {"source": "repository", "revision": "a" * 40}, "coverage": {"files_read": 1}}
    version = GraphSnapshot.from_data(snapshot).version
    s.create_project(owner, {"id": project, "name": "100%_ready!", "repo_url": "https://github.com/test/repo",
                             "snapshot": snapshot, "snapshot_version": version, "ready": True})
    ident = s.enqueue(owner, project, {"source": "private"}, require_project=True)
    assert s.finish(s.claim(), {"kind": "analysis", "partial_results": True, "risk_score": 25.5,
                               "commit_sha": "b" * 40, "snapshot_version": version, "_snapshot": snapshot})
    listed = s.list_jobs(owner, query="%_", status="partial", limit=1)
    assert listed["total"] == 1 and listed["analyses"][0]["id"] == ident
    assert listed["analyses"][0]["risk_score"] == 25.5
    assert listed["analyses"][0]["partial_results"] is True
    assert "payload" not in listed["analyses"][0] and "result" not in listed["analyses"][0]
    assert s.list_jobs(owner, query="%' OR 1=1 --")["total"] == 0
    assert s.list_jobs(pg_case.other)["total"] == 0
    assert s.list_jobs(owner, offset=1)["analyses"] == []
    assert s.snapshot_metadata(project, owner)[0]["coverage"] == {"files_read": 1}
    assert s.set_project_baseline(project, owner, version)["baseline_version"] == version
    s.delete_project(project, owner)
    assert s.snapshot_metadata(project, owner) == [] and s.get("baseline", project, owner) is None


def test_postgres_baseline_delete_and_finish_leave_no_orphaned_capture(pg_case):
    from core.store import ProjectNotFound
    s, owner, project = pg_case.store, pg_case.owner, pg_case.project
    snapshot = {"services": [{"name": "api"}]}
    s.create_project(owner, {"id": project, "snapshot": snapshot, "snapshot_version": "version", "ready": True})
    s.enqueue(owner, project, {}, require_project=True)
    job = s.claim()
    def select():
        try:
            s.set_project_baseline(project, owner, "version")
        except ProjectNotFound:
            pass
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(select), pool.submit(s.finish, job, {"_snapshot": snapshot, "snapshot_version": "version"}),
                   pool.submit(s.delete_project, project, owner)]
        for future in futures:
            future.result(timeout=20)
    assert s.snapshot_metadata(project, owner) == []
    assert s.get("baseline", project, owner) is None
    assert s.list_jobs(owner)["total"] == 0
