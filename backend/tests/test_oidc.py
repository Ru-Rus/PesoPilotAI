"""Full Authlib exchange against deterministic discovery/token/JWKS HTTP fixtures."""
import hashlib
import base64
import time
from urllib.parse import parse_qs, urlparse
import httpx
import pytest
from authlib.jose import JsonWebKey, jwt
from sqlalchemy import select
from app.auth import oauth, SESSION_COOKIE, FLOW_COOKIE, digest
from app.db import settings
from app.models import AuthEvent, AuthSession, LoginFlow, User

@pytest.fixture
def provider(monkeypatch):
    key = JsonWebKey.generate_key('RSA', 2048, is_private=True, options={'kid': 'fixture-key'})
    wrong_key = JsonWebKey.generate_key('RSA', 2048, is_private=True, options={'kid': 'fixture-key'})
    state = {'nonce': '', 'fault': None, 'challenge': ''}
    issuer = settings.oidc_issuer
    def handler(request):
        if request.url.path.endswith('/.well-known/openid-configuration'):
            return httpx.Response(200, json={'issuer': issuer, 'authorization_endpoint': issuer + '/authorize', 'token_endpoint': issuer + '/token', 'jwks_uri': issuer + '/jwks', 'id_token_signing_alg_values_supported': ['RS256'], 'end_session_endpoint': issuer + '/logout'})
        if request.url.path.endswith('/jwks'):
            return httpx.Response(200, json={'keys': [key.as_dict(is_private=False)]})
        if request.url.path.endswith('/token'):
            data = parse_qs(request.content.decode())
            assert data['redirect_uri'][0] == settings.frontend_url + '/api/v1/auth/callback'
            verifier = data['code_verifier'][0]
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
            assert challenge == state['challenge']
            claims = {'iss': issuer, 'sub': 'signed-fixture-user', 'aud': settings.oidc_client_id, 'iat': int(time.time()), 'exp': int(time.time()) + 300, 'nonce': state['nonce'], 'name': 'Signed fixture user'}
            fault = state['fault']
            if fault == 'nonce': claims['nonce'] = 'wrong'
            if fault == 'nonce_supported': claims.update(nonce='wrong', nonce_supported=False)
            if fault == 'issuer': claims['iss'] = 'https://evil.example'
            if fault == 'audience': claims['aud'] = 'another-client'
            if fault == 'expiry': claims['exp'] = int(time.time()) - 300
            signed = jwt.encode({'alg': 'RS256', 'kid': 'fixture-key'}, claims, wrong_key if fault == 'signature' else key).decode()
            return httpx.Response(200, json={'access_token': 'fixture-access', 'token_type': 'Bearer', 'id_token': signed})
        raise AssertionError(f'Unexpected provider request: {request.url}')
    monkeypatch.setattr(oauth.keycloak, 'server_metadata', {})
    monkeypatch.setitem(oauth.keycloak.client_kwargs, 'transport', httpx.MockTransport(handler))
    return state

def start(c, provider):
    response = c.get('/api/v1/auth/login', follow_redirects=False)
    assert response.status_code == 302, response.text
    params = parse_qs(urlparse(response.headers['location']).query)
    provider['nonce'] = params['nonce'][0]
    provider['challenge'] = params['code_challenge'][0]
    assert params['code_challenge_method'] == ['S256']
    assert params['prompt'] == ['login']
    return params['state'][0], response

def test_signed_login_rotation_and_flow_replay(client, provider):
    c, factory = client
    previous = c.cookies.get(SESSION_COOKIE)
    state, response = start(c, provider)
    flow_cookie = c.cookies.get(FLOW_COOKIE)
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'Secure' in response.headers['set-cookie']
    result = c.get('/api/v1/auth/callback', params={'state': state, 'code': 'fixture-code'}, follow_redirects=False)
    assert result.status_code == 303, result.text
    assert result.headers['location'] == settings.frontend_url
    session_cookie = c.cookies.get(SESSION_COOKIE)
    assert session_cookie != previous
    cookie = next(x for x in result.headers.get_list('set-cookie') if x.startswith(SESSION_COOKIE + '='))
    assert all(flag in cookie for flag in ('HttpOnly', 'Secure', 'SameSite=lax', 'Path=/'))
    assert 'Domain=' not in cookie
    identity = c.get('/api/v1/auth/me').json()
    assert identity['name'] == 'Signed fixture user'
    with factory() as db:
        assert db.get(AuthSession, digest(previous)) is None
        row = db.get(AuthSession, digest(session_cookie))
        assert row is not None and row.token_hash != session_cookie
        assert db.scalar(select(User).where(User.subject == 'signed-fixture-user')).id == identity['id']
        assert db.scalar(select(AuthEvent).where(AuthEvent.event == 'login_success')) is not None
        assert db.get(LoginFlow, digest(flow_cookie)) is None
    c.cookies.set(FLOW_COOKIE, flow_cookie, domain='localhost.local')
    assert c.get('/api/v1/auth/callback', params={'state': state, 'code': 'fixture-code'}).status_code == 400

@pytest.mark.parametrize('fault', ['state', 'nonce', 'nonce_supported', 'issuer', 'audience', 'expiry', 'signature'])
def test_invalid_oidc_claims_denied(client, provider, fault):
    c, factory = client
    c.cookies.clear()
    provider['fault'] = fault
    state, _ = start(c, provider)
    result = c.get('/api/v1/auth/callback', params={'state': 'forged-state' if fault == 'state' else state, 'code': 'fixture-code'})
    assert result.status_code == 400, result.text
    assert c.cookies.get(SESSION_COOKIE) is None
    with factory() as db:
        assert db.scalar(select(User).where(User.subject == 'signed-fixture-user')) is None
        assert db.scalar(select(AuthEvent).where(AuthEvent.event == 'login_rejected')) is not None


def test_identity_race_without_surviving_user_issues_no_session(client, provider, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session
    c, factory = client
    state, _ = start(c, provider)
    previous = c.cookies.get(SESSION_COOKIE)
    original_commit = Session.commit

    def commit(db):
        if any(isinstance(row, User) and row.subject == 'signed-fixture-user' for row in db.new):
            raise IntegrityError('synthetic concurrent identity change', {}, None)
        return original_commit(db)

    monkeypatch.setattr(Session, 'commit', commit)
    response = c.get('/api/v1/auth/callback', params={'state': state, 'code': 'fixture-code'}, follow_redirects=False)
    assert response.status_code == 503
    assert c.cookies.get(SESSION_COOKIE) == previous
    with factory() as db:
        assert db.scalar(select(AuthEvent).where(AuthEvent.event == 'login_success')) is None
        assert db.scalar(select(User).where(User.subject == 'signed-fixture-user')) is None
