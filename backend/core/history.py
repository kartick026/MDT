"""In-process history store for analysis results."""
import asyncio
import uuid
from typing import List, Dict, Any, Optional


class HistoryStore:
    """Thread-safe and async-safe in-memory store for analysis runs."""

    def __init__(self, max_size: int = 200):
        self._history: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._max_size = max_size

    async def add(self, entry: Dict[str, Any]) -> None:
        """Insert a new analysis entry at the beginning, capping at max_size."""
        from core.registry import RegistryManager, current_project_id
        from core.store import get_store
        if current_project_id() is None:
            repo = RegistryManager.repository_key(entry.get("repo_url", ""))
            # Keep the complete result, including evidence and remediation edits.
            serializable = {k: (v.model_dump(mode="json") if hasattr(v, "model_dump") else v) for k, v in entry.items()}
            get_store().put("legacy_analysis", uuid.uuid4().hex, "local", serializable, project=repo)
        async with self._lock:
            self._history.insert(0, entry)
            if len(self._history) > self._max_size:
                self._history.pop()

    async def get_all(self, limit: Optional[int] = None, service: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return a copy of entries, optionally filtered by service and limited."""
        from core.registry import RegistryManager
        from core.store import get_store
        repo = RegistryManager.get_project_context().get("repository_key", "")
        items = get_store().list("legacy_analysis", "local", project=repo, limit=self._max_size)
        if not items:
            async with self._lock:
                items = [r for r in self._history if RegistryManager.repository_key(r.get("repo_url", "")) == repo]

        if service:
            items = [r for r in items if r.get("service") == service]

        if limit is not None:
            return items[:limit]
        return items

    async def clear(self) -> None:
        """Clear all stored history."""
        async with self._lock:
            self._history.clear()
        from core.store import get_store
        with get_store().connection(write=True) as db:
            db.execute("DELETE FROM records WHERE kind='legacy_analysis' AND owner='local'")


history_store = HistoryStore()
