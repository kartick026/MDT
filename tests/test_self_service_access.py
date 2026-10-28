"""Self-service access must enable useful work without granting global privileges."""
from fastapi.testclient import TestClient
import pytest

from app import app
from core.config import settings
from core.auth import create_access_token


@pytest.mark.parametrize('profile,signup,expected', [
    ('local', True, 'analyst'), ('local', False, 'viewer'), ('hosted', False, 'viewer'),
])
def test_new_social_role_follows_deployment_policy(isolate_durable_store, monkeypatch, profile, signup, expected):
    monkeypatch.setattr(settings, 'RUNTIME_PROFILE', profile)
    monkeypatch.setattr(settings, 'ALLOW_SELF_SIGNUP', signup)
    account = isolate_durable_store.neon_account('https://provider.example', 'new-user', {'email':'new@example.com'})
    assert account['role'] == expected
    assert account['role'] != 'admin'


def test_existing_read_only_account_is_not_implicitly_promoted(isolate_durable_store):
    store = isolate_durable_store
    store.create_account('restricted', {'email':'read@example.com', 'provider':'neon', 'role':'viewer',
                                      'neon_subject':'subject', 'neon_issuer':'https://provider.example'})
    account = store.neon_account('https://provider.example', 'subject', {'email':'read@example.com'})
    assert account['role'] == 'viewer' and account['username'] == 'restricted'


def test_new_verified_social_user_can_create_and_analyze_only_owned_projects(isolate_durable_store, monkeypatch):
    import core.neon_auth as provider
    monkeypatch.setattr(provider, 'verified_neon_identity', lambda token: ('https://provider.example','new-subject',{'email':'new@example.com'}))
    client = TestClient(app)
    login = client.post('/auth/oauth-login', json={'id_token':'verified-provider-token-placeholder'})
    assert login.status_code == 200
    data = login.json()
    assert data['user']['role'] == 'analyst'
    headers = {'Authorization':'Bearer ' + data['access_token']}
    created = client.post('/v1/projects', headers=headers, json={'name':'Own project','repo_url':settings.DEMO_REPO_URL,'use_demo':True})
    assert created.status_code == 201, created.text
    own_id = created.json()['id']
    store = isolate_durable_store
    store.put('project','other-project','another-user',{'id':'other-project','ready':True})
    assert [item['id'] for item in client.get('/v1/projects',headers=headers).json()['projects']] == [own_id]
    assert client.get('/v1/projects/other-project',headers=headers).status_code == 404
    assert client.post('/v1/projects/other-project/analyses',headers=headers,json={'source':'import'}).status_code == 404
    assert client.post('/v1/projects/' + own_id + '/analyses',headers=headers,json={'source':'import'}).status_code == 202
    assert client.post('/auth/invite',headers=headers,json={'username':'promote-me','password':'valid-test-password'}).status_code == 403
    # Supplying an admin claim does not change the stored role.
    forged_role = {'Authorization':'Bearer ' + create_access_token({'sub':data['user']['username'],'role':'admin'})}
    assert client.get('/auth/me',headers=forged_role).json()['role'] == 'analyst'


def test_local_password_signup_ignores_requested_admin_role(isolate_durable_store, monkeypatch, tmp_path):
    import core.auth as auth
    monkeypatch.setattr(auth, 'USERS_FILE', tmp_path/'users.json')
    response = TestClient(app).post('/auth/register',json={'username':'new-local-user','password':'valid-test-password','role':'admin'})
    assert response.status_code == 201 and response.json()['user']['role'] == 'analyst'


def test_invite_only_signup_stays_disabled(monkeypatch):
    monkeypatch.setattr(settings,'ALLOW_SELF_SIGNUP',False)
    response = TestClient(app).post('/auth/register',json={'username':'not-invited','password':'valid-test-password'})
    assert response.status_code == 403
