"""Shared, dependency-free setup for scripts run directly or with ``python -m``."""
import importlib.util
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def ensure_runtime(modules, requirements=None):
    """Use an existing project venv when the selected Python lacks dependencies."""
    missing = [name for name in modules if importlib.util.find_spec(name) is None]
    if not missing:
        return
    probe = "import importlib.util,json,sys; sys.exit(any(importlib.util.find_spec(n) is None for n in json.loads(sys.argv[1])))"
    for name in (".venv-alpha", ".venv"):
        for relative in ("Scripts/python.exe", "bin/python"):
            candidate = ROOT / name / relative
            if not candidate.is_file() or candidate.resolve() == Path(sys.executable).resolve():
                continue
            try:
                check = subprocess.run([str(candidate), "-c", probe, json.dumps(modules)],
                                       capture_output=True, timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                continue
            if check.returncode == 0:
                print(f"Using project Python: {candidate}", flush=True)
                raise SystemExit(subprocess.call([str(candidate), str(Path(sys.argv[0]).resolve()), *sys.argv[1:]]))
    raise SystemExit(
        "Missing Python dependencies: " + ", ".join(missing) + ".\n"
        "Install them in the project environment (Python 3.11 is the deployment target):\n"
        "  python -m venv .venv-alpha\n"
        "  .venv-alpha/Scripts/python.exe -m pip install " + (requirements or "-r backend/requirements-hosted.txt -r requirements-test.txt") + "\n"
        "On Linux/macOS use .venv-alpha/bin/python. Then rerun this script."
    )


def add_backend_path():
    for path in (ROOT, ROOT / "backend"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def backend_source():
    for candidate in (ROOT / "backend", ROOT, Path("/app")):
        if (candidate / "core" / "config.py").is_file():
            return candidate
    raise SystemExit("Backend source not found; run from a full project checkout or backend image.")


@contextmanager
def isolated_backend():
    """Load application engines from a disposable copy with no live credentials."""
    from scripts.test_isolated import IGNORE, isolated_environment
    previous_cwd, previous_path, previous_env = Path.cwd(), sys.path[:], dict(os.environ)
    with tempfile.TemporaryDirectory(prefix="mdt-offline-") as directory:
        target = Path(directory)
        shutil.copytree(backend_source(), target / "backend", ignore=IGNORE)
        try:
            os.chdir(target)
            sys.path.insert(0, str(target / "backend"))
            env = isolated_environment(target, previous_env)
            env.update(PASSWORD_AUTH_ENABLED="false", ADMIN_PASSWORD="", AUDITOR_PASSWORD="")
            env["MDT_ISOLATED_BACKEND"] = str(target / "backend")
            os.environ.clear()
            os.environ.update(env)
            yield target
        finally:
            os.chdir(previous_cwd)
            sys.path[:] = previous_path
            os.environ.clear()
            os.environ.update(previous_env)
