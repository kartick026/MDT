"""Credential loading and scan output regressions; no real credentials or network."""
import pytest

from scripts.check_secrets import Finding, environment_file, scan_text
from scripts.test_neon_db import database_url_from_env


def url(value):
    return 'postgresql://' + 'unit-user:' + value + '@example.invalid/unit-db'


def test_database_check_uses_ignored_env_files_with_expected_precedence(tmp_path, monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    (tmp_path / 'backend').mkdir()
    (tmp_path / '.env').write_text('DATABASE_URL=' + url('root-unit-value'))
    (tmp_path / 'backend' / '.env').write_text('DATABASE_URL=' + url('backend-unit-value'))
    assert database_url_from_env(tmp_path) == url('root-unit-value')
    monkeypatch.setenv('DATABASE_URL', url('process-unit-value'))
    assert database_url_from_env(tmp_path) == url('process-unit-value')


def test_database_check_supports_backend_env_and_fails_without_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(SystemExit, match='Set DATABASE_URL'):
        database_url_from_env(tmp_path)
    (tmp_path / 'backend').mkdir()
    (tmp_path / 'backend' / '.env').write_text('DATABASE_URL=' + url('backend-unit-value'))
    assert database_url_from_env(tmp_path) == url('backend-unit-value')


def test_credential_detection_returns_locations_without_values():
    password = 'random-' + 'A92j' * 6
    text = 'DATABASE = "' + url(password) + '"'
    findings = scan_text('scripts/probe.py', text)
    assert findings == [Finding('scripts/probe.py', 1, 'database credential')]
    assert password not in repr(findings)


def test_scan_detects_vendor_tokens_even_outside_connection_strings():
    token = 'npg_' + 'A2b4' * 5
    assert scan_text('config.py', 'password = "' + token + '"')[0].kind == 'Neon password'


def test_scan_detects_private_key_material_without_flagging_documentation_headers():
    header = '-----BEGIN ' + 'PRIVATE KEY-----'
    assert not scan_text('docs/setup.md', header + '\\nyour-key-content\\n')
    assert scan_text('key.pem', header + '\n' + 'A' * 64)[0].kind == 'private key'


def test_environment_variants_are_private_and_templates_do_not_bypass_secret_scans():
    for name in ['.env', 'backend/.env.production', 'frontend/.env.local', 'production.env', 'local.env.backup']:
        assert environment_file(name)
    for name in ['backend/.env.example', 'backend/hosted.env.example', '.env.template']:
        assert not environment_file(name)
    assert scan_text('backend/.env.example', 'DATABASE_URL=' + url('a-realistic-credential-9212'))
    assert not scan_text('backend/.env.example', 'DATABASE_URL=' + url('your_password'))
