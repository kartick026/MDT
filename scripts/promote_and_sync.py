"""Preview a narrowly scoped account/ownership migration; no changes without --apply.

Both source owner and destination account must be named explicitly. Only selected
project IDs are transferred. Existing accounts, history and code are never deleted.
"""
import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._runtime import add_backend_path, ensure_runtime
from scripts._database import configured_database_url, diagnostic_main, readonly_connection


def execute(db, sql, args=()):
    if hasattr(db, "pgconn"):
        sql = sql.replace("?", "%s")
    return db.execute(sql, args)


def plan_migration(db, account, from_owner, projects, promote=False):
    row = execute(db, "SELECT payload FROM records WHERE kind='account' AND id=? AND owner='auth'", (account,)).fetchone()
    if not row:
        raise ValueError("Destination account does not exist")
    profile = json.loads(row["payload"])
    changes = []
    for project in projects:
        saved = execute(db, "SELECT id FROM records WHERE kind='project' AND id=? AND owner=?", (project, from_owner)).fetchone()
        if not saved:
            raise ValueError("A selected project does not belong to the specified source owner")
        count = execute(db, "SELECT COUNT(*) AS n FROM records WHERE owner=? AND project=?", (from_owner, project)).fetchone()["n"]
        jobs = execute(db, "SELECT COUNT(*) AS n FROM jobs WHERE owner=? AND project=?", (from_owner, project)).fetchone()["n"]
        changes.append({"project": project, "records": count, "jobs": jobs})
    return profile, changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True, help="Existing destination account ID")
    parser.add_argument("--promote-admin", action="store_true", help="Explicitly give this named account admin privileges")
    parser.add_argument("--from-owner", help="Source owner ID; required for transfers")
    parser.add_argument("--project", action="append", default=[], help="Transfer only this project ID; repeat as needed")
    parser.add_argument("--apply", action="store_true", help="Apply the printed, explicitly scoped changes")
    args = parser.parse_args()
    if args.project and not args.from_owner:
        parser.error("--project requires --from-owner")
    if args.from_owner and not args.project:
        parser.error("--from-owner requires at least one --project; unbounded bulk transfers are disabled")
    if not args.project and not args.promote_admin:
        parser.error("Select --promote-admin and/or specific --project IDs")
    ensure_runtime(("dotenv", "psycopg", "pydantic_settings"))
    url = configured_database_url()
    if args.apply:
        add_backend_path()
        from core.store import Store
        connection = Store(url).connection(write=True)
    else:
        connection = readonly_connection(url)
    with connection as db:
        profile, changes = plan_migration(db, args.account, args.from_owner, args.project, args.promote_admin)
        if args.apply:
            if args.promote_admin:
                profile["role"] = "admin"
                execute(db, "UPDATE records SET payload=? WHERE kind='account' AND id=? AND owner='auth'",
                        (json.dumps(profile), args.account))
            for change in changes:
                execute(db, "UPDATE records SET owner=? WHERE owner=? AND project=?", (args.account, args.from_owner, change["project"]))
                execute(db, "UPDATE jobs SET owner=? WHERE owner=? AND project=?", (args.account, args.from_owner, change["project"]))
    print(json.dumps({"applied": args.apply, "account": args.account, "promote_admin": args.promote_admin, "transfers": changes}))
    return 0


if __name__ == "__main__":
    raise SystemExit(diagnostic_main(main))
