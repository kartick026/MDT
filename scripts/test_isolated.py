"""Run tests in a disposable source copy, excluding credentials and runtime data."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="mdt-tests-") as directory:
    target = Path(directory).resolve()
    assert target.is_relative_to(Path(tempfile.gettempdir()).resolve())
    ignore = shutil.ignore_patterns(".env", ".env.*", "data", "__pycache__", "*.pyc", "chroma_db")
    for name in ("backend", "tests", "mdt-hook"):
        shutil.copytree(root / name, target / name, ignore=ignore)
    shutil.copy2(root / "pytest.ini", target / "pytest.ini")
    env = {**os.environ, "TESTING": "true", "RUNTIME_PROFILE": "local", "ENVIRONMENT": "test",
           "OPENAI_API_KEY": "", "GITHUB_TOKEN": "", "GITHUB_APP_PRIVATE_KEY": "", "GITHUB_APP_ID": "",
           "ADMIN_USERNAME": "admin", "ADMIN_PASSWORD": "admin123", "AUDITOR_USERNAME": "auditor", "AUDITOR_PASSWORD": "auditor123",
           "AUTH_REQUIRED": "true", "ALLOW_SELF_SIGNUP": "true", "ENABLE_DEFAULT_VIEWER": "true",
           "DATABASE_URL": str(target / "test.sqlite3"), "NEO4J_URI": "bolt://127.0.0.1:1",
           "PYTHONPATH": str(target / "backend")}
    result = subprocess.run([sys.executable, "-m", "pytest", *(sys.argv[1:] or ["-q", "--tb=short"])], cwd=target, env=env)
    raise SystemExit(result.returncode)
