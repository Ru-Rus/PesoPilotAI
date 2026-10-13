from datetime import timedelta
import pytest
from sqlalchemy import select
from app.auth import SESSION_COOKIE, digest, now
from app.db import settings
from app.models import AuthEvent, AuthSession

@pytest.mark.parametrize('method,path,kwargs', [
    ('get', '/api/v1/accounts', {}),
    ('post', '/api/v1/accounts', {'json': {'name': 'No', 'kind': 'cash'}}),
    ('get', '/api/v1/transactions', {}),
    ('post', '/api/v1/transactions', {'json': {'account_id': 1, 'occurred_at': '2026-10-01', 'description': 'No', 'category': 'Other', 'kind': 'expense', 'amount': '1.00'}}),
    ('delete', '/api/v1/transactions/1', {}),
    ('post', '/api/v1/budgets', {'json': {'month': '2026-10', 'category': 'Other', 'amount': '1.00'}}),
    ('get', '/api/v1/analytics/summary?month=2026-10', {}),
    ('post', '/api/v1/imports/preview', {'data': {'account_id': 1}, 'files': {'file': ('x.csv', b'bad', 'text/csv')}}),
    ('post', '/api/v1/imports/confirm', {'data': {'account_id': 1, 'digest': 'bad'}, 'files': {'file': ('x.csv', b'bad', 'text/csv')}}),
    ('get', '/api/v1/auth/me', {}),
    ('post', '/api/v1/auth/logout', {}),
])
def test_all_protected_routes_deny_anonymous(client, method, path, kwargs):
    c, _ = client
    c.cookies.clear()
    assert c.request(method.upper(), path, **kwargs).status_code == 401

@pytest.mark.parametrize('reason', ['absolute', 'idle'])
def test_session_expiration(client, reason):
    c, factory = client
    token = c.cookies.get(SESSION_COOKIE)
    with factory() as db:
        row = db.get(AuthSession, digest(token))
        if reason == 'absolute':
            row.expires_at = now() - timedelta(seconds=1)
        else:
            row.last_seen_at = now() - timedelta(seconds=settings.session_idle_seconds + 1)
        db.commit()
    assert c.get('/api/v1/accounts').status_code == 401
    with factory() as db:
        assert db.get(AuthSession, digest(token)) is None
        assert db.scalar(select(AuthEvent).where(AuthEvent.event == 'session_expired')) is not None

def test_cookie_security_logout_and_replay(client, monkeypatch):
    c, factory = client
    token = c.cookies.get(SESSION_COOKIE)
    async def metadata():
        return {'end_session_endpoint': 'http://localhost:8080/realms/pesopilot/protocol/openid-connect/logout'}
    from app.auth import oauth
    monkeypatch.setattr(oauth.keycloak, 'load_server_metadata', metadata)
    result = c.post('/api/v1/auth/logout')
    assert result.status_code == 200
    cookie = result.headers.get_list('set-cookie')[0]
    assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=lax' in cookie and 'Path=/' in cookie
    assert 'Domain=' not in cookie
    assert c.get('/api/v1/accounts').status_code == 401
    c.cookies.set(SESSION_COOKIE, token, domain='localhost.local')
    assert c.get('/api/v1/accounts').status_code == 401
    with factory() as db:
        assert db.get(AuthSession, digest(token)) is None
        assert db.scalar(select(AuthEvent).where(AuthEvent.event == 'logout')) is not None

@pytest.mark.parametrize('headers', [{}, {'Origin': 'https://evil.example', 'X-CSRF-Token': 'bad'}, {'Origin': settings.frontend_url, 'X-CSRF-Token': 'bad'}])
def test_csrf_denied(client, headers):
    c, _ = client
    c.headers.pop('X-CSRF-Token', None)
    c.headers.pop('Origin', None)
    assert c.post('/api/v1/accounts', json={'name': 'No', 'kind': 'cash'}, headers=headers).status_code == 403

def test_rate_limit(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(settings, 'api_limit', 2)
    assert c.get('/api/v1/accounts').status_code == 200
    result = c.get('/api/v1/accounts')
    assert result.status_code == 429
    assert 'Retry-After' in result.headers

def test_login_rate_limit(client, monkeypatch):
    c, _ = client
    c.cookies.clear()
    monkeypatch.setattr(settings, 'auth_limit', 1)
    assert c.get('/api/v1/auth/callback').status_code == 400
    assert c.get('/api/v1/auth/callback').status_code == 429

def test_unconfigured_login_fails_closed(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(settings, 'oidc_client_secret', '')
    assert c.get('/api/v1/auth/login').status_code == 503

def test_forged_session_denied(client):
    c, _ = client
    c.cookies.clear()
    c.cookies.set(SESSION_COOKIE, 'forged')
    assert c.get('/api/v1/accounts').status_code == 401
