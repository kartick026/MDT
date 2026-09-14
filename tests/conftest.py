import sys
from pathlib import Path
import pytest

# Ensure backend directory is always on sys.path for test discovery
backend_dir = str(Path(__file__).parent.parent / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.utils import reset_rate_limit_records
from core.registry import RegistryManager, REGISTRY_FILE


@pytest.fixture(autouse=True)
def clean_rate_limit_state():
    """Ensure in-memory rate limit records do not leak across test cases."""
    reset_rate_limit_records()
    yield
    reset_rate_limit_records()


@pytest.fixture(autouse=True)
def isolate_registry_state():
    """Ensure registry.json on disk and RegistryManager in-memory cache do not leak across test cases."""
    initial_content = None
    if REGISTRY_FILE.exists():
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                initial_content = f.read()
        except Exception:
            pass

    yield

    with RegistryManager._lock:
        RegistryManager._cache = None

    if initial_content is not None:
        try:
            with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
                f.write(initial_content)
        except Exception:
            pass
    elif REGISTRY_FILE.exists():
        try:
            REGISTRY_FILE.unlink()
        except Exception:
            pass

    with RegistryManager._lock:
        RegistryManager._cache = None

