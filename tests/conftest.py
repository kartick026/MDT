import sys
from pathlib import Path

# Ensure backend directory is always on sys.path for test discovery
backend_dir = str(Path(__file__).parent.parent / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
