"""Exercise the real durable store in disposable SQLite files, never live data.

These are queue/recovery invariants and local timings, not deployed HTTP SLOs.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.readiness_common import ROOT, evidence, write_report


def database_digest(store):
    with store.connection() as db:
        content = {table: [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()]
                   for table, order in (("records", "kind,id"), ("jobs", "id"))}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def exercise(directory, concurrency):
    os.environ.setdefault("TESTING", "true")
    sys.path.insert(0, str(ROOT / "backend"))
    from core.config import settings
    from core.store import Store

    store = Store(str(Path(directory) / "queue.sqlite3"))
    checks = []

    def verify(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    started = time.perf_counter()
    def submit(index):
        before = time.perf_counter()
        ident = store.enqueue(f"owner-{index}", "fixture", {"source": "synthetic"},
                              f"request-{index}", f"fingerprint-{index}")
        return ident, (time.perf_counter() - before) * 1000

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        submissions = list(pool.map(submit, range(concurrency * 4)))
    ids = {item[0] for item in submissions}
    latencies = sorted(item[1] for item in submissions)

    def complete(_):
        completed = []
        while (job := store.claim()) is not None:
            verify_result = store.finish(job, {"kind": "fixture", "partial_results": False})
            completed.append((job["id"], verify_result))
        return completed

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        completed = [item for batch in pool.map(complete, range(concurrency)) for item in batch]
    verify("each admitted job claimed and finished exactly once", len(completed) == len(ids)
           and {item[0] for item in completed} == ids and all(item[1] for item in completed))
    cycle_seconds = time.perf_counter() - started

    def quota_attempt(_):
        try:
            return store.enqueue("quota-owner", "fixture", {})
        except ValueError as error:
            if "quota" not in str(error).lower():
                raise
            return None
    attempts = max(concurrency * 2, settings.MAX_ACTIVE_JOBS_PER_USER + 2)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        accepted = list(pool.map(quota_attempt, range(attempts)))
    verify("concurrent admission respects account quota", sum(x is not None for x in accepted)
           == min(settings.MAX_ACTIVE_JOBS_PER_USER, settings.MAX_JOBS_PER_DAY))
    while (job := store.claim()) is not None:
        store.finish(job, {"kind": "fixture"})

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        duplicates = list(pool.map(lambda _: store.enqueue("dedupe", "fixture", {"source": "same"},
            "same-key", "same-fingerprint"), range(concurrency * 2)))
    verify("simultaneous retries create one job", len(set(duplicates)) == 1)
    old = store.claim()
    with store.connection(write=True) as db:
        db.execute("UPDATE jobs SET expires=? WHERE id=?", (time.time() - 1, old["id"]))
    restarted = Store(store.path)
    recovered = restarted.claim()
    verify("restart recovers expired lease", recovered["id"] == old["id"] and recovered["lease"] != old["lease"])
    verify("stale worker cannot publish", not store.finish(old, {"wrong": True}))
    verify("recovered worker can publish", restarted.finish(recovered, {"recovered": True}))

    cancel_id = store.enqueue("cancel-owner", "fixture", {"source": "private fixture"})
    active = store.claim()
    verify("other owner cannot cancel or read", store.cancel(cancel_id, "outsider") is None
           and store.job(cancel_id, "outsider") is None)
    store.cancel(cancel_id, "cancel-owner")
    verify("cancel fences active worker", not store.finish(active, {"wrong": True})
           and store.job(cancel_id, "cancel-owner")["status"] == "cancelled")

    crash_id = store.enqueue("crash-owner", "fixture", {"source": "private fixture"})
    for _ in range(3):
        crashed = store.claim()
        verify("interrupted job retains identity", crashed is not None and crashed["id"] == crash_id)
        with store.connection(write=True) as db:
            db.execute("UPDATE jobs SET expires=? WHERE id=?", (time.time() - 1, crash_id))
    verify("repeated interruption terminates", store.claim() is None
           and store.job(crash_id, "crash-owner")["status"] == "failed")
    with store.connection() as db:
        remaining = db.execute("SELECT COUNT(*) AS n FROM jobs WHERE payload <> '{}' ").fetchone()["n"]
    verify("terminal jobs discard uploaded source", remaining == 0)

    before_digest = database_digest(store)
    recovery_started = time.perf_counter()
    with closing(sqlite3.connect(store.path)) as source, closing(sqlite3.connect(str(Path(directory) / "restored.sqlite3"))) as target:
        source.backup(target)
    restored = Store(str(Path(directory) / "restored.sqlite3"))
    verify("quiescent backup restores every row", database_digest(restored) == before_digest)
    recovery_seconds = time.perf_counter() - recovery_started
    verify("restored store remains writable", bool(restored.enqueue("restored-owner", "fixture", {})))
    return {"status": "passed", "checks": checks, "concurrency": concurrency,
            "jobs_completed": len(completed), "cycle_seconds": cycle_seconds,
            "enqueue_p95_ms": latencies[math.ceil(len(latencies) * .95) - 1],
            "backup_restore_seconds": recovery_seconds, "restored_digest": before_digest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    policy = json.loads((ROOT / "readiness-policy.json").read_text())["operations"]
    concurrency = policy["pilot_concurrency"] * policy["test_concurrency_multiplier"]
    with TemporaryDirectory(prefix="mdt-readiness-") as directory:
        try:
            result = exercise(directory, concurrency)
        except Exception as error:
            result = {"status": "failed", "failure": type(error).__name__ + ": " + str(error)}
    report = evidence("local_reliability", environment="disposable_local_sqlite", **result,
        scope="Store-level synthetic workload only; no HTTP load, deployed database, infrastructure outage, or live-data recovery verified")
    write_report(args.output, report)
    print(json.dumps({"status": report["status"], "output": str(args.output), "failure": result.get("failure")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
