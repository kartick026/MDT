"""Portable read-only database inspection used by the command-line entry points."""
import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._database import configured_database_url, diagnostic_main, readonly_connection, safe_repository
from scripts._runtime import ROOT, ensure_runtime


def payload(row):
    try:
        value = json.loads(row["payload"] or "{}")
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def records_and_jobs(db, projects_only=False):
    query = "SELECT kind, id, owner, project, payload FROM records"
    if projects_only:
        query += " WHERE kind='project'"
    records = db.execute(query + " ORDER BY kind,id").fetchall()
    print("Records:", len(records))
    for row in records:
        value = payload(row)
        print(f"[{row['kind']}] id={row['id']} owner={row['owner']} project={row['project']}")
        if row["kind"] == "project":
            print(f"  Name: {value.get('name', '')} | Repo: {safe_repository(value.get('repo_url'))}")
    jobs = db.execute("SELECT id, owner, project, status, stage FROM jobs ORDER BY created DESC").fetchall()
    print("Jobs:", len(jobs))
    for row in jobs:
        print(f"[job] id={row['id']} owner={row['owner']} project={row['project']} status={row['status']} stage={row['stage']}")


def dependencies(db):
    rows = db.execute("SELECT id, kind, payload FROM records WHERE kind IN ('snapshot', 'project') ORDER BY created DESC LIMIT 5").fetchall()
    for row in rows:
        value = payload(row)
        relations = value.get("dependencies") or (value.get("snapshot") or {}).get("dependencies") or []
        print(f"[{row['kind']}] {row['id']}: {len(relations)} dependencies")
        for relation in relations[:10]:
            print("  " + json.dumps({key: relation.get(key) for key in ("from", "to", "type")}, ensure_ascii=True))


def main(mode):
    parser = argparse.ArgumentParser(description="Inspect MDT data in a read-only transaction. No payloads or connection credentials are printed.")
    parser.add_argument("--sqlite", metavar="PATH", help="Inspect this existing SQLite file instead of the configured database")
    args = parser.parse_args()
    if mode == "sqlite" and not args.sqlite:
        paths = sorted({path.resolve() for directory in (ROOT / "backend" / "data", ROOT / "data")
                        if directory.is_dir() for pattern in ("*.sqlite3", "*.db") for path in directory.glob(pattern)})
        if not paths:
            raise SystemExit("No local SQLite databases found. Use --sqlite PATH, or inspect_db.py for the configured PostgreSQL database.")
    else:
        if args.sqlite:
            paths = [args.sqlite]
        elif mode == "legacy":
            paths = [str(ROOT / "backend" / "data" / "mdt.sqlite3")]
        else:
            ensure_runtime(("dotenv", "psycopg"))
            paths = [configured_database_url()]
    for path in paths:
        with readonly_connection(str(path)) as db:
            if mode == "dependencies":
                dependencies(db)
            elif mode == "sqlite":
                tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                print("SQLite file:", path)
                print("Tables:", ", ".join(sorted(tables)))
                if {"records", "jobs"} <= tables:
                    records_and_jobs(db)
            else:
                records_and_jobs(db, projects_only=mode == "legacy")


def run(mode):
    return diagnostic_main(lambda: main(mode))
