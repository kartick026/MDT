"""Read-only diagnostic connections; never initialize or migrate the app store."""
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import sys
from urllib.parse import parse_qsl, urlsplit, urlunsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._runtime import ROOT


def configured_database_url(root=None, postgres_only=False):
    from dotenv import dotenv_values
    root = Path(root) if root is not None else ROOT
    values = {**dotenv_values(root / "backend" / ".env"), **dotenv_values(root / ".env"), **os.environ}
    url = (values.get("DATABASE_URL") or "").strip()
    if postgres_only and not url.startswith(("postgresql://", "postgres://")):
        raise SystemExit("Set DATABASE_URL in .env or backend/.env before running this check.")
    return url or str(root / "backend" / "data" / "mdt.sqlite3")


@contextmanager
def readonly_connection(url):
    if url.startswith(("postgresql://", "postgres://")):
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(url, row_factory=dict_row, connect_timeout=10) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            options = dict(parse_qsl(urlsplit(url).query)).get("options", "")
            if "search_path" not in options:
                db.execute("SET LOCAL search_path TO mdt, public")
            yield db
    else:
        path = Path(url.removeprefix("sqlite:///")).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file():
            raise SystemExit("SQLite database does not exist. Use --sqlite PATH to inspect an existing database.")
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()


def safe_repository(value):
    parts = urlsplit(str(value or ""))
    if parts.scheme and parts.netloc:
        return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", ""))
    return str(value or "")


class ReadonlyStore:
    """Store-shaped reader for migration planning, with no schema initialization."""
    def __init__(self, url):
        self.url = url
        self.postgres = url.startswith(("postgresql://", "postgres://"))

    @contextmanager
    def connection(self, write=False):
        if write:
            raise ValueError("Read-only migration plans cannot write")
        with readonly_connection(self.url) as db:
            if self.postgres:
                class Adapter:
                    def execute(_, sql, args=()):
                        return db.execute(sql.replace("?", "%s"), args)
                yield Adapter()
            else:
                yield db


def diagnostic_main(action):
    """Keep driver exceptions from echoing a URL or credential to the terminal."""
    try:
        return action()
    except (OSError, ValueError, sqlite3.Error) as error:
        raise SystemExit(f"Database check failed ({type(error).__name__}). Check configuration and database access.") from None
    except Exception as error:
        import psycopg
        if isinstance(error, psycopg.Error):
            raise SystemExit(f"Database check failed ({type(error).__name__}). Check configuration and database access.") from None
        raise
