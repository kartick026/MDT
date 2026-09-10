"""In-process history store for analysis results."""
import asyncio
from typing import List, Dict, Any, Optional


class HistoryStore:
    """Thread-safe and async-safe in-memory store for analysis runs."""

    def __init__(self, max_size: int = 200):
        self._history: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._max_size = max_size

    async def add(self, entry: Dict[str, Any]) -> None:
        """Insert a new analysis entry at the beginning, capping at max_size."""
        async with self._lock:
            self._history.insert(0, entry)
            if len(self._history) > self._max_size:
                self._history.pop()

    async def get_all(self, limit: Optional[int] = None, service: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return a copy of entries, optionally filtered by service and limited."""
        async with self._lock:
            items = list(self._history)

        if service:
            items = [r for r in items if r.get("service") == service]

        if limit is not None:
            return items[:limit]
        return items

    async def clear(self) -> None:
        """Clear all stored history."""
        async with self._lock:
            self._history.clear()


history_store = HistoryStore()
