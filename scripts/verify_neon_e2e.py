"""Run store integration tests against an explicitly configured disposable PostgreSQL database.

Set TEST_DATABASE_URL in the shell first. DATABASE_URL and saved application data
are never used for this test. For a read-only live connection check, use test_neon_db.py.
"""
import argparse
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run_e2e_test():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url.startswith(("postgresql://", "postgres://")):
        parser.error("Set TEST_DATABASE_URL to a disposable PostgreSQL database. Use test_neon_db.py for a read-only check of the saved database.")
    from scripts._runtime import ensure_runtime
    ensure_runtime(("dotenv", "psycopg", "pytest", "pytest_asyncio", "pytest_httpx"))
    from scripts._database import configured_database_url
    if url == configured_database_url():
        parser.error("TEST_DATABASE_URL must be separate from the configured application DATABASE_URL.")
    from scripts.test_isolated import main
    return main(["--with-integrations", "tests/test_store_postgres.py", "-q", "--tb=short"])


if __name__ == "__main__":
    raise SystemExit(run_e2e_test())
