"""Run pytest in a disposable source copy, excluding credentials and runtime data.

Usage: python scripts/test_isolated.py -q
Pass --with-integrations to explicitly allow TEST_DATABASE_URL / MDT_LIVE_NEO4J_*.
All other arguments are forwarded to pytest. No running application is required.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._runtime import ROOT, ensure_runtime

INTEGRATION_KEYS = ("TEST_DATABASE_URL", "MDT_LIVE_NEO4J_URI", "MDT_LIVE_NEO4J_USER", "MDT_LIVE_NEO4J_PASSWORD")
SOURCE_DIRS = ("backend", "tests", "mdt-hook", "scripts", "evaluation", "services",
               "fixtures", "demo", "docs", "frontend", "extensions", "packages")
IGNORE = shutil.ignore_patterns(".env", ".env.*", "*.env", "*.env.*", "data", "chroma_db",
    "node_modules", ".git", ".venv*", "__pycache__", "*.pyc", ".pytest_cache", "dist", "build",
    "*.pem", "*.key", "*.png", "*.jpg", "*.jpeg", "*.pdf")


def copy_sources(root, target):
    for name in SOURCE_DIRS:
        if (root / name).is_dir():
            shutil.copytree(root / name, target / name, ignore=IGNORE)
    for source in root.iterdir():
        if (source.is_file() and source.suffix in {".ini", ".toml", ".json", ".yaml", ".yml", ".md", ".txt"}
                and not IGNORE(str(root), [source.name])):
            shutil.copy2(source, target / source.name)


def isolated_environment(target, inherited, integrations=False):
    # Start clean: shell credentials, pytest options/plugins and live service URLs
    # must not silently change the test run or point it at saved application data.
    system = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE",
              "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "LANG", "LC_ALL", "COMSPEC", "PATHEXT"}
    env = {key: value for key, value in inherited.items() if key.upper() in system}
    env.update(TESTING="true", RUNTIME_PROFILE="local", ENVIRONMENT="test",
        OPENAI_API_KEY="", GITHUB_TOKEN="", GITHUB_APP_PRIVATE_KEY="", GITHUB_APP_ID="",
        ADMIN_USERNAME="admin", ADMIN_PASSWORD="unit-admin-password-strong-2026",
        AUDITOR_USERNAME="auditor", AUDITOR_PASSWORD="unit-auditor-password-strong-2026",
        PASSWORD_AUTH_ENABLED="true",
        AUTH_REQUIRED="true", ALLOW_SELF_SIGNUP="true", ENABLE_DEFAULT_VIEWER="true",
        DATABASE_URL=str(target / "test.sqlite3"), NEO4J_URI="bolt://127.0.0.1:1",
        CHROMADB_MODE="local", JWT_SECRET_KEY="isolated-tests-signing-key-over-32-characters",
        PYTHONPATH=os.pathsep.join((str(target), str(target / "backend"))),
        PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    if integrations:
        env.update({key: inherited[key] for key in INTEGRATION_KEYS if key in inherited})
    return env


def pytest_arguments(arguments, root):
    result = []
    for argument in arguments:
        path, *selector = argument.split("::", 1)
        if Path(path).is_absolute() and Path(path).is_relative_to(root):
            path = Path(path).relative_to(root).as_posix()
            argument = path + ("::" + selector[0] if selector else "")
        result.append(argument)
    return result


def main(argv=None):
    ensure_runtime(("pytest", "pytest_asyncio", "pytest_httpx", "dotenv", "psycopg",
                    "fastapi", "pydantic_settings", "httpx", "git", "jwt", "bcrypt", "yaml", "tree_sitter"))
    arguments = list(sys.argv[1:] if argv is None else argv)
    integrations = "--with-integrations" in arguments
    arguments = [arg for arg in arguments if arg != "--with-integrations"]
    with tempfile.TemporaryDirectory(prefix="mdt-tests-") as directory:
        target = Path(directory)
        copy_sources(ROOT, target)
        env = isolated_environment(target, os.environ, integrations)
        print("Running tests in a disposable copy. Integration services: " + ("explicitly enabled" if integrations else "disabled"), flush=True)
        command = [sys.executable, "-m", "pytest", "-p", "pytest_asyncio.plugin", "-p", "pytest_httpx",
                   *pytest_arguments(arguments or ["-q", "--tb=short"], ROOT)]
        return subprocess.call(command, cwd=target, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
