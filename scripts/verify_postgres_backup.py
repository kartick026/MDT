"""Read-only verification of an MDT PostgreSQL restore, without printing data.

Set MDT_BACKUP_SOURCE_URL and MDT_BACKUP_RESTORE_URL to quiet databases. URLs
must point to different databases. This does not create, restore or drop tables.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._runtime import ensure_runtime
from scripts._database import diagnostic_main


def fingerprints(url):
    import psycopg
    result = {}
    with psycopg.connect(url, connect_timeout=10) as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        for table, order in (("records", "kind,id"), ("jobs", "id"), ("schema_versions", "version")):
            digest, count = hashlib.sha256(), 0
            with db.cursor(name="verify_" + table) as cursor:
                # Identifiers come from the fixed tuple above, never user input.
                cursor.execute("SELECT * FROM mdt." + table + " ORDER BY " + order)
                for row in cursor:
                    digest.update(json.dumps(row, default=str, separators=(",", ":")).encode())
                    digest.update(b"\n")
                    count += 1
            result[table] = {"rows": count, "sha256": digest.hexdigest()}
    return result


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    ensure_runtime(("dotenv", "psycopg"))
    from dotenv import load_dotenv
    from scripts._runtime import ROOT
    load_dotenv(ROOT / '.env')
    load_dotenv(ROOT / 'backend' / '.env')
    source, restored = os.environ.get("MDT_BACKUP_SOURCE_URL"), os.environ.get("MDT_BACKUP_RESTORE_URL")
    if not source or not restored or source == restored:
        raise SystemExit("Set distinct MDT_BACKUP_SOURCE_URL and MDT_BACKUP_RESTORE_URL values.")
    before, after = fingerprints(source), fingerprints(restored)
    if before != after:
        raise SystemExit("Restore differs from source. Keep the original database; inspect the restore while writes are paused.")
    print(json.dumps({"verified": True, "tables": before}))


if __name__ == "__main__":
    raise SystemExit(diagnostic_main(main))
