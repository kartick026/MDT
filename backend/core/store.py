"""Durable alpha records and leased jobs, using SQLite locally or PostgreSQL.

Every data lookup includes an owner. Jobs carry an immutable input snapshot;
workers publish only while they still own the lease. No credentials in logs.
Schema changes are additive and recorded by an explicit migration version.
"""
import json
import sqlite3
import time
import uuid
from urllib.parse import urlsplit, parse_qsl
from contextlib import contextmanager
from pathlib import Path
from functools import lru_cache

from core.config import settings


class IdempotencyConflict(ValueError):
    pass


class ProjectNotFound(ValueError):
    pass


class Store:
    def __init__(self, url=""):
        self.postgres = url.startswith(("postgresql://", "postgres://"))
        self.url = url
        # Keep hosted tables outside Supabase's exposed public schema. Explicit
        # search_path options support isolated integration-test schemas.
        options = dict(parse_qsl(urlsplit(url).query)).get("options", "") if self.postgres else ""
        self.private_schema = self.postgres and "search_path" not in options
        self.path = url.removeprefix("sqlite:///") if url else str(Path(__file__).parent.parent / "data" / "mdt.sqlite3")
        if not self.postgres:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS schema_versions (version INTEGER PRIMARY KEY)")
            db.execute("""CREATE TABLE IF NOT EXISTS records (
                kind TEXT NOT NULL, id TEXT NOT NULL, owner TEXT NOT NULL,
                project TEXT NOT NULL, payload TEXT NOT NULL, created DOUBLE PRECISION NOT NULL,
                PRIMARY KEY(kind,id))""")
            db.execute("CREATE INDEX IF NOT EXISTS records_owner ON records(kind,owner,project,created)")
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, project TEXT NOT NULL,
                status TEXT NOT NULL, stage TEXT NOT NULL, payload TEXT NOT NULL,
                result TEXT, error TEXT, created DOUBLE PRECISION NOT NULL,
                updated DOUBLE PRECISION NOT NULL, lease TEXT, expires DOUBLE PRECISION,
                attempts INTEGER NOT NULL DEFAULT 0, dedupe TEXT UNIQUE)""")
            db.execute("CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status,created)")
            db.execute("CREATE INDEX IF NOT EXISTS jobs_owner_history ON jobs(owner,created,id)")
            db.execute("INSERT INTO schema_versions(version) VALUES(1) ON CONFLICT(version) DO NOTHING")

    @contextmanager
    def connection(self, write=False):
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            db = psycopg.connect(self.url, row_factory=dict_row, connect_timeout=10)
            if self.private_schema:
                db.execute("CREATE SCHEMA IF NOT EXISTS mdt")
                db.execute("SET search_path TO mdt")
            class Adapter:
                def execute(_, sql, args=()):
                    return db.execute(sql.replace("?", "%s"), args)
            handle = Adapter()
        else:
            db = sqlite3.connect(self.path, timeout=15)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA busy_timeout=15000")
            if write:
                db.execute("BEGIN IMMEDIATE")
            handle = db
        try:
            yield handle
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def put(self, kind, ident, owner, payload, project=""):
        with self.connection(write=True) as db:
            changed = db.execute("""INSERT INTO records(kind,id,owner,project,payload,created) VALUES(?,?,?,?,?,?)
                ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload WHERE records.owner=excluded.owner""",
                (kind, ident, owner, project, json.dumps(payload, default=str), time.time())).rowcount
            if not changed:
                raise ValueError("Record belongs to another owner")

    def create_account(self, username, payload):
        with self.connection(write=True) as db:
            changed = db.execute("INSERT INTO records(kind,id,owner,project,payload,created) VALUES('account',?,'auth','',?,?) ON CONFLICT(kind,id) DO NOTHING", (username, json.dumps(payload), time.time())).rowcount
            if not changed:
                raise ValueError("That username is already in use.")

    def neon_account(self, issuer, subject, profile):
        """Bind a verified provider subject without renaming existing data owners."""
        import hashlib
        email = profile['email'].strip().lower()
        with self.connection(write=True) as db:
            self._lock_owner(db, 'auth')
            accounts = [dict(row) for row in db.execute("SELECT id,payload FROM records WHERE kind='account' AND owner='auth'").fetchall()]
            legacy = None
            for row in accounts:
                account = json.loads(row['payload'])
                if account.get('neon_subject') == subject and account.get('neon_issuer') == issuer:
                    return {**account, 'username': row['id']}
                if (not account.get('neon_subject') and account.get('email', '').strip().lower() == email
                        and account.get('provider') in {'google', 'github', 'neon'}
                        and row['id'] not in {settings.ADMIN_USERNAME, settings.AUDITOR_USERNAME}):
                    legacy = row, account
            if legacy:
                row, account = legacy
                username = row['id']
            else:
                username = 'neon_' + hashlib.sha256((issuer + '\0' + subject).encode()).hexdigest()[:24]
                account = {'username': username, 'email': email, 'name': profile.get('name') or email,
                           'provider': 'neon', 'avatar_url': profile.get('image') or '',
                           'role': settings.self_service_account_role, 'is_active': True, 'password_hash': ''}
            account.update(neon_subject=subject, neon_issuer=issuer)
            if legacy:
                db.execute("UPDATE records SET payload=? WHERE kind='account' AND id=? AND owner='auth'", (json.dumps(account), username))
            else:
                db.execute("INSERT INTO records(kind,id,owner,project,payload,created) VALUES('account',?,'auth','',?,?)", (username, json.dumps(account), time.time()))
            return {**account, 'username': username}

    def _lock_owner(self, db, owner):
        db.execute("INSERT INTO records(kind,id,owner,project,payload,created) VALUES('quota',?,?,?,'{}',?) ON CONFLICT(kind,id) DO NOTHING", (owner, owner, "", time.time()))
        if self.postgres:
            db.execute("SELECT id FROM records WHERE kind='quota' AND id=? FOR UPDATE", (owner,)).fetchone()

    def create_project(self, owner, project):
        with self.connection(write=True) as db:
            self._lock_owner(db, owner)
            count = db.execute("SELECT COUNT(*) AS n FROM records WHERE kind='project' AND owner=?", (owner,)).fetchone()["n"]
            if count >= settings.MAX_PROJECTS_PER_USER:
                raise ValueError("Project quota reached")
            db.execute("INSERT INTO records(kind,id,owner,project,payload,created) VALUES('project',?,?,?,?,?)", (project["id"], owner, project["id"], json.dumps(project), time.time()))
            if project.get("ready") and project.get("snapshot") and project.get("snapshot_version"):
                self._record_snapshot(db, owner, project["id"], project["snapshot_version"], project["snapshot"])

    def _record_snapshot(self, db, owner, project, version, snapshot, analysis_id=None):
        context = snapshot.get("project", {})
        record = {"snapshot_version": version, "snapshot": snapshot,
                  "captured_at": time.time(), "source_analysis_id": analysis_id,
                  "coverage": snapshot.get("coverage", {}), "project_id": project,
                  "revision": context.get("revision"), "source": context.get("source", "unknown")}
        db.execute("INSERT INTO records(kind,id,owner,project,payload,created) VALUES('snapshot',?,?,?,?,?) ON CONFLICT(kind,id) DO NOTHING",
                   (project + ":" + version, owner, project, json.dumps(record), time.time()))

    def get(self, kind, ident, owner):
        with self.connection() as db:
            row = db.execute("SELECT payload FROM records WHERE kind=? AND id=? AND owner=?", (kind, ident, owner)).fetchone()
            return json.loads(row["payload"]) if row else None

    def list(self, kind, owner, project=None, limit=200):
        sql, args = "SELECT payload FROM records WHERE kind=? AND owner=?", [kind, owner]
        if project is not None:
            sql += " AND project=?"
            args.append(project)
        with self.connection() as db:
            rows = db.execute(sql + " ORDER BY created DESC LIMIT ?", (*args, limit)).fetchall()
            return [json.loads(row["payload"]) for row in rows]

    def delete_project(self, ident, owner):
        with self.connection(write=True) as db:
            # Serialize deletion with project creation and job submission. A
            # delayed API request must not recreate data after deletion wins.
            self._lock_owner(db, owner)
            db.execute("DELETE FROM jobs WHERE project=? AND owner=?", (ident, owner))
            db.execute("DELETE FROM records WHERE owner=? AND (project=? OR (kind='project' AND id=?))", (owner, ident, ident))

    def enqueue(self, owner, project, payload, dedupe=None, fingerprint=None, *, require_project=False):
        now, ident = time.time(), uuid.uuid4().hex
        with self.connection(write=True) as db:
            # A per-owner row lock makes quota checks atomic across PG workers too.
            self._lock_owner(db, owner)
            if require_project and not db.execute(
                "SELECT id FROM records WHERE kind='project' AND id=? AND owner=?",
                (project, owner),
            ).fetchone():
                raise ProjectNotFound("Project not found")
            if dedupe:
                receipt = db.execute("SELECT payload FROM records WHERE kind='idempotency' AND id=? AND owner=?", (dedupe, owner)).fetchone()
                if receipt and json.loads(receipt["payload"]).get("fingerprint") != fingerprint:
                    raise IdempotencyConflict("Idempotency key was already used for different input")
                existing = db.execute("SELECT id FROM jobs WHERE dedupe=? AND owner=?", (dedupe, owner)).fetchone()
                if existing:
                    return existing["id"]
            active = db.execute("SELECT COUNT(*) AS n FROM jobs WHERE owner=? AND status IN ('queued','running')", (owner,)).fetchone()["n"]
            daily = db.execute("SELECT COUNT(*) AS n FROM records WHERE kind='usage' AND owner=? AND created>?", (owner, now - 86400)).fetchone()["n"]
            if active >= settings.MAX_ACTIVE_JOBS_PER_USER or daily >= settings.MAX_JOBS_PER_DAY:
                raise ValueError("Analysis quota reached; wait for a job to finish or the daily window to expire")
            db.execute("INSERT INTO jobs(id,owner,project,status,stage,payload,created,updated,dedupe) VALUES(?,?,?,'queued','queued',?,?,?,?)",
                       (ident, owner, project, json.dumps(payload), now, now, dedupe))
            db.execute("INSERT INTO records(kind,id,owner,project,payload,created) VALUES('usage',?,?,'','{}',?)", (ident, owner, now))
            if dedupe:
                db.execute("INSERT INTO records(kind,id,owner,project,payload,created) VALUES('idempotency',?,?,'',?,?) ON CONFLICT(kind,id) DO NOTHING", (dedupe, owner, json.dumps({"fingerprint": fingerprint}), now))
        return ident

    def claim(self):
        now = time.time()
        with self.connection(write=True) as db:
            # A bounded retry recovers interrupted work without looping forever.
            db.execute("UPDATE jobs SET status='failed',stage='failed',error='Worker interrupted repeatedly',payload='{}' WHERE status='running' AND expires<? AND attempts>=3", (now,))
            suffix = " FOR UPDATE SKIP LOCKED" if self.postgres else ""
            row = db.execute("SELECT * FROM jobs WHERE status='queued' OR (status='running' AND expires<? AND attempts<3) ORDER BY created LIMIT 1" + suffix, (now,)).fetchone()
            if not row:
                return None
            job, lease = dict(row), uuid.uuid4().hex
            db.execute("UPDATE jobs SET status='running',stage='extracting',lease=?,expires=?,updated=?,attempts=attempts+1 WHERE id=?", (lease, now + 60, now, job["id"]))
            job.update(lease=lease, payload=json.loads(job["payload"]))
            return job

    def heartbeat(self, job):
        with self.connection(write=True) as db:
            return db.execute("UPDATE jobs SET expires=?,updated=? WHERE id=? AND lease=? AND status='running'", (time.time()+60, time.time(), job["id"], job["lease"])).rowcount == 1

    def finish(self, job, result=None, error=None):
        status = "failed" if error else ("partial" if result.get("partial_results") else "succeeded")
        with self.connection(write=True) as db:
            self._lock_owner(db, job["owner"])
            changed = db.execute("UPDATE jobs SET status=?,stage=?,result=?,error=?,payload='{}',updated=?,lease=NULL,expires=NULL WHERE id=? AND lease=? AND status='running'",
                                (status, status, json.dumps(result) if result else None, error, time.time(), job["id"], job["lease"])).rowcount
            if changed and result and result.get("kind") == "import":
                result["project"].update(import_status=status, import_error=None)
                db.execute("UPDATE records SET payload=? WHERE kind='project' AND id=? AND owner=?", (json.dumps(result["project"]), job["project"], job["owner"]))
            elif changed and error and job.get("payload", {}).get("input", {}).get("source") == "import":
                row = db.execute("SELECT payload FROM records WHERE kind='project' AND id=? AND owner=?", (job["project"], job["owner"])).fetchone()
                if row:
                    project = json.loads(row["payload"])
                    project.update(import_status="failed", import_error=error)
                    db.execute("UPDATE records SET payload=? WHERE kind='project' AND id=? AND owner=?", (json.dumps(project), job["project"], job["owner"]))
            if changed and result:
                snapshot = result.get("_snapshot") or result.get("project", {}).get("snapshot")
                if snapshot and result.get("snapshot_version"):
                    self._record_snapshot(db, job["owner"], job["project"], result["snapshot_version"], snapshot, job["id"])
            return bool(changed)

    def list_jobs(self, owner, project=None, status=None, query="", limit=20, offset=0):
        """Project only summary fields in SQL; never load source or full snapshots."""
        def field(column, key):
            return f"({column}::jsonb ->> '{key}')" if self.postgres else f"json_extract({column}, '$.{key}')"
        name, repo = field("p.payload", "name"), field("p.payload", "repo_url")
        commit, base = field("j.result", "commit_sha"), field("j.result", "base_sha")
        where, args = [], []
        if owner:
            where.append("j.owner=?")
            args.append(owner)
        if project:
            where.append("j.project=?")
            args.append(project)
        if status:
            where.append("j.status=?")
            args.append(status)
        if query:
            # Treat user wildcards literally; both supported DBs accept ESCAPE.
            pattern = "%" + query.lower().replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
            where.append("(" + " OR ".join(f"LOWER(COALESCE({item},'')) LIKE ? ESCAPE '!'" for item in ("j.id", name, repo, commit, base)) + ")")
            args.extend([pattern] * 5)
        tail = " FROM jobs j LEFT JOIN records p ON p.kind='project' AND p.id=j.project" + (" WHERE " + " AND ".join(where) if where else "")
        columns = ["j.id", "j.project", "j.status", "j.stage", "j.created", "j.updated", "j.error",
                   name + " AS project_name", repo + " AS repo_url", commit + " AS commit_sha", base + " AS base_sha"]
        columns.extend(field("j.result", key) + " AS " + key for key in ("kind", "risk_score", "architecture_smell_score", "snapshot_version", "partial_results"))
        with self.connection() as db:
            total = db.execute("SELECT COUNT(*) AS n" + tail, args).fetchone()["n"]
            rows = db.execute("SELECT " + ",".join(columns) + tail + " ORDER BY j.created DESC,j.id DESC LIMIT ? OFFSET ?", (*args, limit, offset)).fetchall()
        summaries = [dict(row) for row in rows]
        for item in summaries:
            for key in ("risk_score", "architecture_smell_score"):
                item[key] = float(item[key]) if item[key] is not None else None
            item["partial_results"] = item["partial_results"] in (True, 1, "true")
        return {"analyses": summaries, "total": total, "limit": limit, "offset": offset}

    def snapshot_metadata(self, project, owner, limit=200):
        def field(key):
            return f"(payload::jsonb ->> '{key}')" if self.postgres else f"json_extract(payload, '$.{key}')"
        columns = [field(key) + " AS " + key for key in
                   ("snapshot_version", "captured_at", "source_analysis_id", "revision", "source", "coverage")]
        with self.connection() as db:
            rows = db.execute("SELECT " + ",".join(columns) + " FROM records WHERE kind='snapshot' AND project=? AND owner=? ORDER BY created DESC,id DESC LIMIT ?",
                              (project, owner, limit)).fetchall()
        result = [dict(row) for row in rows]
        for item in result:
            item["captured_at"] = float(item["captured_at"])
            item["coverage"] = json.loads(item["coverage"]) if item["coverage"] else {}
        return result

    def set_project_baseline(self, project, owner, version):
        """Validate and persist a baseline in the deletion serialization boundary."""
        with self.connection(write=True) as db:
            self._lock_owner(db, owner)
            row = db.execute("SELECT payload FROM records WHERE kind='project' AND id=? AND owner=?", (project, owner)).fetchone()
            if not row:
                raise ProjectNotFound("Project not found")
            captured = db.execute("SELECT id FROM records WHERE kind='snapshot' AND id=? AND owner=? AND project=?",
                                  (project + ":" + version, owner, project)).fetchone()
            if not captured:
                current = json.loads(row["payload"])
                # Compatibility for projects created before snapshot archiving.
                if not current.get("ready") or current.get("snapshot_version") != version or not current.get("snapshot"):
                    raise ValueError("Captured snapshot not found")
                self._record_snapshot(db, owner, project, version, current["snapshot"])
            result = {"project_id": project, "baseline_version": version, "updated_at": time.time()}
            db.execute("INSERT INTO records(kind,id,owner,project,payload,created) VALUES('baseline',?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload WHERE records.owner=excluded.owner",
                       (project, owner, project, json.dumps(result), time.time()))
        return result

    def put_project_record(self, kind, ident, owner, project, payload):
        """Serialize annotations/baselines with project deletion."""
        with self.connection(write=True) as db:
            self._lock_owner(db, owner)
            if not db.execute("SELECT id FROM records WHERE kind='project' AND id=? AND owner=?", (project, owner)).fetchone():
                raise ProjectNotFound("Project not found")
            changed = db.execute("INSERT INTO records(kind,id,owner,project,payload,created) VALUES(?,?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload WHERE records.owner=excluded.owner",
                                 (kind, ident, owner, project, json.dumps(payload), time.time())).rowcount
            if not changed:
                raise ValueError("Record belongs to another owner")

    def job(self, ident, owner):
        with self.connection() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND owner=?", (ident, owner)).fetchone()
        if not row:
            return None
        record = dict(row)
        record.pop("payload", None)
        record.pop("lease", None)
        record.pop("dedupe", None)
        record["result"] = json.loads(record["result"]) if record["result"] else None
        record["job_id"] = record["id"]
        return record

    def cancel(self, ident, owner):
        with self.connection(write=True) as db:
            db.execute("UPDATE jobs SET status='cancelled',stage='cancelled',payload='{}',updated=? WHERE id=? AND owner=? AND status IN ('queued','running')", (time.time(), ident, owner))
        return self.job(ident, owner)

    def prune(self):
        # Retention is explicitly opt-in. A zero limit preserves all durable data,
        # including imported topology captures, historical jobs and review notes.
        if settings.JOB_RETENTION_DAYS <= 0:
            return
        with self.connection(write=True) as db:
            db.execute("DELETE FROM jobs WHERE created<? AND status NOT IN ('queued','running')", (time.time() - settings.JOB_RETENTION_DAYS*86400,))
            analysis_id = "(records.payload::jsonb ->> 'analysis_id')" if self.postgres else "json_extract(records.payload, '$.analysis_id')"
            db.execute("DELETE FROM records WHERE kind LIKE ? AND NOT EXISTS (SELECT 1 FROM jobs WHERE jobs.id=" + analysis_id + " AND jobs.owner=records.owner)", ("finding_review:%",))
            db.execute("DELETE FROM records WHERE kind='usage' AND created<?", (time.time()-2*86400,))
            db.execute("DELETE FROM records WHERE kind='idempotency' AND created<?", (time.time()-settings.JOB_RETENTION_DAYS*86400,))
            for row in db.execute("SELECT id,payload FROM records WHERE kind='revoked'").fetchall():
                if json.loads(row["payload"]).get("expires", 0) < time.time():
                    db.execute("DELETE FROM records WHERE kind='revoked' AND id=?", (row["id"],))
        self._prune_snapshots(time.time() - settings.JOB_RETENTION_DAYS * 86400)

    def _prune_snapshots(self, cutoff):
        # Use a separate transaction after job retention so the lock order stays
        # owner -> project data, matching finish/baseline/delete operations.
        with self.connection() as db:
            candidates = db.execute("SELECT id,owner,project FROM records WHERE kind='snapshot' AND created<?", (cutoff,)).fetchall()
        by_owner = {}
        for row in candidates:
            by_owner.setdefault(row["owner"], []).append(dict(row))
        for owner, captures in by_owner.items():
            with self.connection(write=True) as db:
                self._lock_owner(db, owner)
                protected = {}
                for capture in captures:
                    project = capture["project"]
                    if project not in protected:
                        rows = db.execute("SELECT kind,payload FROM records WHERE kind IN ('project','baseline') AND id=? AND owner=?", (project, owner)).fetchall()
                        protected[project] = {json.loads(row["payload"]).get("snapshot_version" if row["kind"] == "project" else "baseline_version") for row in rows}
                    version = capture["id"][len(project) + 1:]
                    if version not in protected[project]:
                        db.execute("DELETE FROM records WHERE kind='snapshot' AND id=? AND owner=? AND created<?", (capture["id"], owner, cutoff))


@lru_cache(maxsize=1)
def get_store():
    return Store(settings.DATABASE_URL)
