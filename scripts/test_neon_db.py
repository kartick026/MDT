import os
from pathlib import Path

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row


def database_url_from_env(root=None):
    root = root or Path(__file__).resolve().parents[1]
    # Explicit process environment wins; root .env takes precedence over backend/.env.
    load_dotenv(root / ".env")
    load_dotenv(root / "backend" / ".env")
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url.startswith(("postgresql://", "postgres://")):
        raise SystemExit("Set DATABASE_URL in .env or backend/.env before running this check.")
    return database_url


def main():
    database_url = database_url_from_env()
    print("Testing connection to Neon PostgreSQL...")
    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version(), current_database(), current_user;")
            row = cur.fetchone()
            print("Connected successfully!")
            print(f"  Database: {row['current_database']}")
            print(f"  User:     {row['current_user']}")
            print(f"  Version:  {row['version'][:50]}...")

            # Initialize schema
            cur.execute("CREATE TABLE IF NOT EXISTS schema_versions (version INTEGER PRIMARY KEY)")
            cur.execute("""CREATE TABLE IF NOT EXISTS records (
                kind TEXT NOT NULL, id TEXT NOT NULL, owner TEXT NOT NULL,
                project TEXT NOT NULL, payload TEXT NOT NULL, created DOUBLE PRECISION NOT NULL,
                PRIMARY KEY(kind,id))""")
            cur.execute("CREATE INDEX IF NOT EXISTS records_owner ON records(kind,owner,project,created)")
            cur.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, project TEXT NOT NULL,
                status TEXT NOT NULL, stage TEXT NOT NULL, payload TEXT NOT NULL,
                result TEXT, error TEXT, created DOUBLE PRECISION NOT NULL,
                updated DOUBLE PRECISION NOT NULL, lease TEXT, expires DOUBLE PRECISION,
                attempts INTEGER NOT NULL DEFAULT 0, dedupe TEXT UNIQUE)""")
            cur.execute("CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status,created)")
            cur.execute("CREATE INDEX IF NOT EXISTS jobs_owner_history ON jobs(owner,created,id)")
            cur.execute("INSERT INTO schema_versions(version) VALUES(1) ON CONFLICT(version) DO NOTHING")
            conn.commit()

            cur.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('public', 'mdt') ORDER BY table_schema, table_name;")
            tables = cur.fetchall()
            print("Verified tables in Neon database:")
            for t in tables:
                print(f"  - {t['table_schema']}.{t['table_name']}")

if __name__ == "__main__":
    try:
        main()
    except psycopg.Error as exc:
        # A driver error must never echo connection strings or credentials.
        raise SystemExit(f"Database check failed ({type(exc).__name__}). Check DATABASE_URL and database access.") from None
