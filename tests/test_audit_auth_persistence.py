"""Security and preservation regressions, exclusively using isolated stores."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import app
from core.config import settings
from core.local_secrets import local_signing_key


def test_retention_disabled_preserves_every_old_record(isolate_durable_store, monkeypatch):
    store = isolate_durable_store
    monkeypatch.setattr(settings, 'JOB_RETENTION_DAYS', 0)
    store.put('project', 'p', 'admin', {'id': 'p'})
    job = store.enqueue('admin', 'p', {'source': 'patch'})
    store.finish(store.claim(), {'risk_score': 7, 'architecture_smell_score': 0})
    store.put('snapshot', 'p:old', 'admin', {'snapshot_version': 'old'}, 'p')
    store.put('finding_review:f1', 'note', 'admin', {'analysis_id': job}, 'p')
    store.put('revoked', 'old', 'auth', {'expires': 1})
    with store.connection(write=True) as db:
        db.execute('UPDATE records SET created=1')
        db.execute('UPDATE jobs SET created=1')
        before = {table: [dict(row) for row in db.execute('SELECT * FROM ' + table)] for table in ['records', 'jobs']}
    store.prune()
    with store.connection() as db:
        after = {table: [dict(row) for row in db.execute('SELECT * FROM ' + table)] for table in ['records', 'jobs']}
    assert after == before


def test_local_key_is_atomic_and_survives_process_style_reopens(tmp_path):
    filename = str(tmp_path / 'keys' / 'jwt.key')
    with ThreadPoolExecutor(max_workers=8) as pool:
        keys = list(pool.map(lambda _: local_signing_key(filename), range(16)))
    assert len(set(keys)) == 1
    token = jwt.encode({'sub': 'admin'}, keys[0], algorithm='HS256')
    assert jwt.decode(token, local_signing_key(filename), algorithms=['HS256'])['sub'] == 'admin'


def test_invalid_persisted_key_is_not_replaced(tmp_path):
    filename = tmp_path / 'jwt.key'
    filename.write_text('invalid')
    with pytest.raises(ValueError, match='restore'):
        local_signing_key(str(filename))
    assert filename.read_text() == 'invalid'


def test_client_profile_cannot_impersonate_admin_or_get_a_token():
    client = TestClient(app)
    response = client.post('/auth/oauth-login', json={'email': 'admin@attacker.example', 'provider': 'google'})
    assert response.status_code == 422
    assert 'access_token' not in response.json()
    assert client.post('/auth/verify-neon-session', json={'verifier': 'any-known-identifier'}).status_code == 410


def test_database_outage_is_unavailable_not_invalid_credentials(monkeypatch):
    import core.store as store_module
    from core.auth import create_access_token
    token = create_access_token({'sub': settings.ADMIN_USERNAME, 'role': 'admin'})
    monkeypatch.setattr(store_module, 'get_store', lambda: (_ for _ in ()).throw(ConnectionError('offline')))
    response = TestClient(app).get('/auth/me', headers={'Authorization': 'Bearer ' + token})
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_health_distinguishes_provider_configuration_from_availability(monkeypatch):
    from api import health
    monkeypatch.setattr(settings, 'OPENAI_API_KEY', 'synthetic-test-key')
    monkeypatch.setattr(health, 'check_neo4j_health', lambda: {'status': 'healthy', 'connected': True})
    monkeypatch.setattr(health, 'check_chroma_health', lambda: {'status': 'uninitialized', 'connected': False})
    result = await health.detailed_health(user=None)
    llm = result['components']['details']['llm']
    assert llm['status'] == 'configured' and llm['availability'] == 'not_probed'
    assert llm['project_analysis_mode'] == 'deterministic'


def test_provider_subject_binding_preserves_legacy_owner_and_data(isolate_durable_store):
    store = isolate_durable_store
    store.create_account('existing-owner', {'username': 'existing-owner', 'email': 'owner@example.com',
                         'provider': 'google', 'role': 'analyst', 'is_active': True, 'password_hash': 'preserved'})
    store.put('project', 'p', 'existing-owner', {'id': 'p', 'name': 'Preserved'})
    original = store.get('project', 'p', 'existing-owner')
    account = store.neon_account('https://provider.example', 'subject-1', {'email': 'owner@example.com'})
    assert account['username'] == 'existing-owner'
    assert account['role'] == 'analyst' and account['password_hash'] == 'preserved'
    assert store.get('project', 'p', 'existing-owner') == original
    # Same subject, changed email: retain ownership. Same email, different subject: never inherit it.
    assert store.neon_account('https://provider.example', 'subject-1', {'email': 'changed@example.com'})['username'] == 'existing-owner'
    other = store.neon_account('https://provider.example', 'subject-2', {'email': 'owner@example.com'})
    assert other['username'] != 'existing-owner' and other['role'] == 'analyst'
    assert store.get('project', 'p', other['username']) is None


def test_provider_email_prefix_never_links_to_seeded_admin(isolate_durable_store):
    store = isolate_durable_store
    account = store.neon_account('https://provider.example', 'subject', {'email': settings.ADMIN_USERNAME + '@example.com'})
    assert account['username'] != settings.ADMIN_USERNAME and account['role'] == 'analyst'


def test_admin_lists_and_opens_same_foreign_owned_history(isolate_durable_store):
    from core.auth import create_access_token
    store = isolate_durable_store
    store.create_account('other', {'role': 'analyst', 'is_active': True})
    store.put('project', 'foreign-project', 'other', {'id': 'foreign-project', 'ready': True, 'snapshot': {}})
    ident = store.enqueue('other', 'foreign-project', {'source': 'patch'})
    store.finish(store.claim(), {'risk_score': 3})
    client = TestClient(app)
    headers = {'Authorization': 'Bearer ' + create_access_token({'sub': settings.ADMIN_USERNAME})}
    assert client.get('/v1/projects/foreign-project', headers=headers).status_code == 200
    history = client.get('/v1/analyses?project_id=foreign-project', headers=headers)
    assert history.status_code == 200 and history.json()['total'] == 1
    assert client.get('/v1/analyses/' + ident, headers=headers).status_code == 200
    # A non-default admin uses the same role check, never a magic username.
    store.create_account('second-admin', {'role': 'admin', 'is_active': True})
    headers = {'Authorization': 'Bearer ' + create_access_token({'sub': 'second-admin'})}
    assert client.get('/v1/analyses/' + ident, headers=headers).status_code == 200
    store.create_account('viewer', {'role': 'viewer', 'is_active': True})
    headers = {'Authorization': 'Bearer ' + create_access_token({'sub': 'viewer', 'role': 'admin'})}
    assert client.get('/v1/analyses/' + ident, headers=headers).status_code == 404
    assert client.get('/v1/analyses?project_id=foreign-project', headers=headers).status_code == 404


def test_append_only_restore_is_idempotent_and_conflicts_roll_back(isolate_durable_store, tmp_path):
    from core.store import Store
    from scripts.restore_legacy_store import restore_legacy
    source = Store(str(tmp_path / 'legacy.sqlite3'))
    source.put('project', 'old', 'admin', {'id': 'old', 'name': 'Old project'})
    ident = source.enqueue('admin', 'old', {})
    source.finish(source.claim(), {'risk_score': None, 'architecture_smell_score': 0})
    target = isolate_durable_store
    target.put('project', 'current', 'admin', {'id': 'current', 'name': 'Current project'})
    assert restore_legacy(source.path, target)['added']['jobs'] == 1
    assert target.job(ident, 'admin') is None
    result = restore_legacy(source.path, target, apply=True)
    assert result['added']['jobs'] == 1
    assert target.get('project', 'current', 'admin')['name'] == 'Current project'
    assert target.job(ident, 'admin')['result']['risk_score'] is None
    assert restore_legacy(source.path, target, apply=True)['added'] == {'records': 0, 'jobs': 0}
    source.put('project', 'old', 'admin', {'id': 'old', 'name': 'Conflicting'})
    source.put('project', 'new', 'admin', {'id': 'new'})
    with pytest.raises(ValueError, match='Conflicting'): restore_legacy(source.path, target, apply=True)
    assert target.get('project', 'old', 'admin')['name'] == 'Old project'
    assert target.get('project', 'new', 'admin') is None


def test_inactive_social_account_cannot_sign_in(isolate_durable_store, monkeypatch):
    import core.neon_auth as provider
    store = isolate_durable_store
    store.create_account('inactive', {'username': 'inactive', 'email': 'x@example.com', 'provider': 'neon',
                                    'neon_subject': 's', 'neon_issuer': 'https://issuer', 'is_active': False})
    monkeypatch.setattr(provider, 'verified_neon_identity', lambda token: ('https://issuer', 's', {'email': 'x@example.com'}))
    assert TestClient(app).post('/auth/oauth-login', json={'id_token': 'signed-token-placeholder'}).status_code == 403


@pytest.mark.parametrize('case', ['valid', 'tampered', 'wrong_issuer', 'expired', 'unsigned', 'unknown_user', 'unverified'])
def test_provider_jwt_requires_signature_issuer_expiry_and_verified_user(case, monkeypatch):
    import core.neon_auth as provider
    import core.store as store_module
    private = ed25519.Ed25519PrivateKey.generate()
    monkeypatch.setattr(settings, 'NEON_AUTH_URL', 'https://provider.example/neondb/auth')
    monkeypatch.setattr(settings, 'NEON_JWKS_URL', 'https://provider.example/neondb/auth/jwks')
    monkeypatch.setattr(provider, '_jwks_client', lambda url: SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private.public_key())))
    row = {'id': 's', 'name': 'User', 'email': 'user@example.com', 'image': None, 'emailVerified': case != 'unverified'}
    class DB:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, query, args):
            assert args == ('s',) and 'updatedAt' not in query
            return SimpleNamespace(fetchone=lambda: None if case == 'unknown_user' else row)
    monkeypatch.setattr(store_module, 'get_store', lambda: SimpleNamespace(postgres=True, connection=lambda: DB()))
    claims = {'sub': 's', 'iss': 'https://wrong.example' if case == 'wrong_issuer' else 'https://provider.example',
              'iat': int(time.time()) - 60, 'exp': int(time.time()) + (-1 if case == 'expired' else 60)}
    token = jwt.encode(claims, private, algorithm='EdDSA')
    if case == 'tampered': token = jwt.encode({**claims, 'sub': 'admin'}, ed25519.Ed25519PrivateKey.generate(), algorithm='EdDSA')
    if case == 'unsigned': token = jwt.encode(claims, None, algorithm='none')
    if case == 'valid':
        assert provider.verified_neon_identity(token) == ('https://provider.example', 's', row)
    else:
        with pytest.raises(HTTPException) as error: provider.verified_neon_identity(token)
        assert error.value.status_code == 401
