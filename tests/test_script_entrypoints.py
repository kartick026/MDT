"""CLI regressions: isolated credentials, portable paths and read-only diagnostics."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import socket

import pytest

from scripts._database import diagnostic_main, readonly_connection
from scripts._runtime import ROOT
from scripts.test_isolated import copy_sources, isolated_environment, pytest_arguments
from scripts.run_microservices import check_ports


def test_runner_excludes_credentials_runtime_state_and_builds(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    for relative in ("backend/.env", "backend/production.env", "backend/.env.backup", "backend/private.key",
                     "backend/data/saved.sqlite3", "frontend/node_modules/dependency/index.js",
                     "frontend/dist/index.html", "backend/core/engine.py", "services/user_service/main.py",
                     "fixtures/input.json", "docs/guide.md", "frontend/src/app.tsx", "pytest.ini"):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    copy_sources(source, target)
    copied = {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()}
    assert copied == {"backend/core/engine.py", "services/user_service/main.py", "fixtures/input.json",
                      "docs/guide.md", "frontend/src/app.tsx", "pytest.ini"}
    assert (source / "backend/data/saved.sqlite3").read_text() == "fixture"


def test_runner_requires_opt_in_for_live_integration_settings(tmp_path):
    inherited = {"PATH": "system-path", "DATABASE_URL": "saved-database", "NEO4J_URI": "saved-graph",
                 "TEST_DATABASE_URL": "explicit-test-db", "MDT_LIVE_NEO4J_PASSWORD": "explicit-test-password",
                 "OPENAI_API_KEY": "private-key", "PYTEST_ADDOPTS": "--unexpected-option",
                 "JWT_SECRET_FILE": "saved-signing-key"}
    env = isolated_environment(tmp_path, inherited)
    assert env["PATH"] == "system-path"
    assert not {"saved-database", "saved-graph", "private-key", "saved-signing-key"} & set(env.values())
    assert "TEST_DATABASE_URL" not in env and "MDT_LIVE_NEO4J_PASSWORD" not in env
    assert "PYTEST_ADDOPTS" not in env
    assert env["PASSWORD_AUTH_ENABLED"] == "true"
    assert env["ADMIN_PASSWORD"].startswith("unit-")
    enabled = isolated_environment(tmp_path, inherited, integrations=True)
    assert enabled["TEST_DATABASE_URL"] == "explicit-test-db"
    assert enabled["MDT_LIVE_NEO4J_PASSWORD"] == "explicit-test-password"
    assert enabled["DATABASE_URL"] == str(tmp_path / "test.sqlite3")


def test_absolute_test_selector_is_remapped_to_the_disposable_copy():
    selector = str(ROOT / "tests/test_auth.py") + "::test_example"
    assert pytest_arguments([selector, "-q"], ROOT) == ["tests/test_auth.py::test_example", "-q"]


def test_readonly_sqlite_cannot_write_or_create_a_database(tmp_path):
    path = tmp_path / "saved.sqlite3"
    with pytest.raises(SystemExit, match="does not exist"):
        with readonly_connection(str(path)):
            pass
    assert not path.exists()
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE existing (value TEXT)")
    before = path.read_bytes()
    with readonly_connection(str(path)) as db:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("DROP TABLE existing")
    assert path.read_bytes() == before


@pytest.mark.parametrize("script", ["inspect_db.py", "inspect_deps.py", "inspect_sqlite.py", "dump_sqlite_repos.py"])
def test_inspection_scripts_work_from_other_directories_without_mutating_data(script, tmp_path):
    path = tmp_path / "saved.sqlite3"
    hidden = "sensitive-payload-value"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE records (kind TEXT, id TEXT, owner TEXT, project TEXT, payload TEXT, created REAL)")
        db.execute("CREATE TABLE jobs (id TEXT, owner TEXT, project TEXT, status TEXT, stage TEXT, created REAL)")
        db.execute("INSERT INTO records VALUES ('project','p1','owner','p1',?,1)",
                   (json.dumps({"name": "Saved project", "token": hidden,
                                "repo_url": "https://user:" + hidden + "@github.com/example/repo?token=" + hidden}),))
        db.execute("INSERT INTO jobs VALUES ('j1','owner','p1','succeeded','done',1)")
    before = path.read_bytes()
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--sqlite", str(path)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert hidden not in result.stdout + result.stderr
    assert path.read_bytes() == before


def test_driver_error_message_cannot_echo_a_connection_secret():
    def fail():
        raise ValueError("credential-in-driver-error")
    with pytest.raises(SystemExit) as caught:
        diagnostic_main(fail)
    assert "ValueError" in str(caught.value)
    assert "credential-in-driver-error" not in str(caught.value)


def test_e2e_refuses_to_use_default_database(tmp_path):
    before = {path: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    env = {key: value for key, value in os.environ.items() if key != "TEST_DATABASE_URL"}
    result = subprocess.run([sys.executable, str(ROOT / "scripts/verify_neon_e2e.py")],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 2
    assert "Set TEST_DATABASE_URL" in result.stderr
    assert {path: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()} == before


def test_all_script_modules_import_without_starting_services_or_changing_environment(tmp_path):
    code = ("import importlib,os,socket,sys; from pathlib import Path; "
            "sys.path.insert(0,sys.argv[1]); before=dict(os.environ); "
            "[importlib.import_module('scripts.'+p.stem) for p in sorted((Path(sys.argv[1])/'scripts').glob('*.py'))]; "
            "assert dict(os.environ)==before; print('All script imports are inert')")
    result = subprocess.run([sys.executable, "-c", code, str(ROOT)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "All script imports are inert" in result.stdout


def test_port_conflict_does_not_close_or_stop_the_existing_listener():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        with pytest.raises(SystemExit, match="already in use"):
            check_ports("127.0.0.1", [port])
        assert listener.fileno() != -1
        assert listener.getsockname()[1] == port


@pytest.mark.parametrize("script,arguments", [
    ("api_smoke.py", ["--allow-write"]),
    ("hosted_smoke.py", ["prepare"]),
    ("promote_and_sync.py", ["--account", "recipient", "--from-owner", "source"]),
])
def test_mutating_scripts_require_explicit_scope_before_any_data_access(script, arguments, tmp_path):
    env = dict(os.environ)
    env.pop("MDT_SMOKE_TOKEN", None)
    env.pop("MDT_SMOKE_PASSWORD", None)
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *arguments],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 2


def test_scoped_account_migration_is_a_readonly_preview_by_default(tmp_path):
    path = tmp_path / "migration.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE records (kind TEXT,id TEXT,owner TEXT,project TEXT,payload TEXT)")
        db.execute("CREATE TABLE jobs (id TEXT,owner TEXT,project TEXT)")
        db.execute("INSERT INTO records VALUES ('account','recipient','auth','',?)", (json.dumps({"role": "analyst"}),))
        db.execute("INSERT INTO records VALUES ('project','p1','source','p1','{}')")
        db.execute("INSERT INTO records VALUES ('project','p2','unrelated','p2','{}')")
        db.execute("INSERT INTO jobs VALUES ('j1','source','p1')")
    before = path.read_bytes()
    env = {**os.environ, "DATABASE_URL": str(path)}
    result = subprocess.run([sys.executable, str(ROOT / "scripts/promote_and_sync.py"),
        "--account", "recipient", "--promote-admin", "--from-owner", "source", "--project", "p1"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["applied"] is False
    assert plan["transfers"] == [{"project": "p1", "records": 1, "jobs": 1}]
    assert path.read_bytes() == before


def test_hosted_smoke_supports_disabled_production_openapi(monkeypatch):
    import urllib.error
    from scripts import hosted_smoke
    calls = []
    def request(path):
        calls.append(path)
        if path == '/health/ready':
            return {'status': 'ready', 'profile': 'hosted'}
        raise urllib.error.HTTPError('https://example.invalid' + path, 404, 'Not found', {}, None)
    monkeypatch.setattr(hosted_smoke, 'request', request)
    hosted_smoke.verify_hosted_boundaries()
    assert '/openapi.json' in calls and '/services/graph' in calls


def test_hosted_smoke_rejects_an_exposed_research_route(monkeypatch):
    from scripts import hosted_smoke
    monkeypatch.setattr(hosted_smoke, 'request', lambda path: {'status': 'ready', 'profile': 'hosted'})
    with pytest.raises(AssertionError, match='route was exposed'):
        hosted_smoke.verify_hosted_boundaries()
