"""Read-only verification of an MDT PostgreSQL restore, without printing data.

Set MDT_BACKUP_SOURCE_URL and MDT_BACKUP_RESTORE_URL to quiet databases. URLs
must point to different databases. This does not create, restore or drop tables.
"""
import hashlib
import json
import os

import psycopg


def fingerprints(url):
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


if __name__ == "__main__":
    source, restored = os.environ.get("MDT_BACKUP_SOURCE_URL"), os.environ.get("MDT_BACKUP_RESTORE_URL")
    if not source or not restored or source == restored:
        raise SystemExit("Set distinct MDT_BACKUP_SOURCE_URL and MDT_BACKUP_RESTORE_URL values.")
    before, after = fingerprints(source), fingerprints(restored)
    if before != after:
        raise SystemExit("Restore differs from source. Keep the original database; inspect the restore while writes are paused.")
    print(json.dumps({"verified": True, "tables": before}))
