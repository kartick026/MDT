import sys
from pathlib import Path
import pytest

# Ensure backend directory is always on sys.path for test discovery
backend_dir = str(Path(__file__).parent.parent / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.utils import reset_rate_limit_records


@pytest.fixture(autouse=True)
def clean_rate_limit_state():
    """Ensure in-memory rate limit records do not leak across test cases."""
    reset_rate_limit_records()
    yield
    reset_rate_limit_records()
