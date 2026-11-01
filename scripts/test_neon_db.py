"""Check the configured PostgreSQL database without changing tables or data."""
import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._runtime import ensure_runtime
from scripts._database import configured_database_url, diagnostic_main, readonly_connection


def database_url_from_env(root=None):
    return configured_database_url(root, postgres_only=True)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    ensure_runtime(("dotenv", "psycopg"))
    with readonly_connection(database_url_from_env()) as db:
        row = db.execute("SELECT version(), current_database(), current_user").fetchone()
        print("PostgreSQL connection successful (read-only).")
        print(f"  Database: {row['current_database']}")
        print(f"  User: {row['current_user']}")
        print(f"  Version: {row['version'].splitlines()[0][:80]}")
        tables = db.execute("SELECT table_schema, table_name FROM information_schema.tables "
                            "WHERE table_schema IN ('public', 'mdt') ORDER BY table_schema, table_name").fetchall()
        for table in tables:
            print(f"  - {table['table_schema']}.{table['table_name']}")


if __name__ == "__main__":
    raise SystemExit(diagnostic_main(main))
