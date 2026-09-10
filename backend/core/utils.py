"""Common utility functions for MDT backend."""
from datetime import datetime, timezone


def now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()
