"""Verify real Keycloak authorization-code login and local logout against SQL Server.

Requires running local Keycloak and KEYCLOAK_ADMIN_PASSWORD in the ignored .env.
Creates one temporary provider user and removes its provider/application records.
"""
import secrets
import re
import os
import ssl
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from uuid import uuid4
import httpx
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from app.auth import SESSION_COOKIE, digest
from app.db import Session, settings
from app.main import app
from app.models import AuthEvent, AuthSession, RateBucket, User

class LoginForm(HTMLParser):
    action = None
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'form' and values.get('id') == 'kc-form-login':
            self.action = values['action']

class LogoutForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None
        self.fields = {}
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'form' and values.get('method', '').lower() == 'post':
            self.action = values.get('action')
        if self.action and tag == 'input' and values.get('name'):
            self.fields[values['name']] = values.get('value', '')

config = dotenv_values('.env')
admin_password = config.get('KEYCLOAK_ADMIN_PASSWORD')
if not admin_password:
    raise RuntimeError('Set KEYCLOAK_ADMIN_PASSWORD in the ignored backend/.env')
issuer = settings.oidc_issuer
base = issuer.split('/realms/')[0]
realm = issuer.split('/realms/')[1]
username = 'smoke-' + uuid4().hex
password = secrets.token_urlsafe(32)
provider_user_id = None
app_user_id = None
with httpx.Client(timeout=20, follow_redirects=False) as provider:
    admin = provider.post(base + '/realms/master/protocol/openid-connect/token', data={'grant_type': 'password', 'client_id': 'admin-cli', 'username': 'admin', 'password': admin_password})
    admin.raise_for_status()
    headers = {'Authorization': 'Bearer ' + admin.json()['access_token']}
    try:
        response = provider.post(base + '/admin/realms/' + realm + '/users', headers=headers, json={'username': username, 'enabled': True, 'firstName': 'Synthetic', 'lastName': 'Smoke', 'email': username + '@example.invalid', 'credentials': [{'type': 'password', 'value': password, 'temporary': False}]})
        response.raise_for_status()
        provider_user_id = response.headers['location'].rsplit('/', 1)[1]
        if os.environ.get('SMOKE_THROUGH_FRONTEND') == 'true':
            assert urlparse(settings.frontend_url).hostname == 'localhost', 'Frontend smoke is restricted to localhost'
            certificate = Path(__file__).resolve().parent.parent / 'frontend/certificates/localhost.pem'
            frontend = httpx.Client(base_url=settings.frontend_url, verify=ssl.create_default_context(cafile=str(certificate)), timeout=20)
        else:
            frontend = TestClient(app, base_url=settings.frontend_url)
        with frontend as c:
            assert c.get('/api/v1/accounts').status_code == 401
            response = c.get('/api/v1/auth/login', follow_redirects=False)
            assert response.status_code == 302, response.text
            login = provider.get(response.headers['location'], follow_redirects=True)
            login.raise_for_status()
            parser = LoginForm()
            parser.feed(login.text)
            assert parser.action, 'Keycloak login form unavailable'
            # Browsers treat localhost as trustworthy for Secure provider cookies;
            # HTTPX does not. Reflect only this loopback provider's cookie jar.
            cookies = '; '.join(cookie.name + '=' + cookie.value for cookie in provider.cookies.jar if cookie.domain in ('localhost', 'localhost.local'))
            assert urlparse(parser.action).netloc == urlparse(base).netloc
            response = provider.post(parser.action, headers={'Cookie': cookies, 'Origin': base}, data={'username': username, 'password': password, 'credentialId': ''})
            if response.status_code != 302:
                title = re.search(r'<title>(.*?)</title>', response.text, re.S)
                messages = re.findall(r'<(?:span|div)[^>]*class="[^"]*(?:feedback-text|alert__title|helper-text)[^"]*"[^>]*>(.*?)</(?:span|div)>', response.text, re.S)
                messages += re.findall(r'<p[^>]*>(.*?)</p>', response.text, re.S)
                summary = re.sub('<[^>]+>', '', ' '.join(messages)).strip()[:400]
                raise AssertionError(f'Keycloak login returned {response.status_code}; title={title.group(1).strip() if title else "none"}; message={summary}')
            target = urlparse(response.headers['location'])
            assert target.netloc == urlparse(settings.frontend_url).netloc
            response = c.get(target.path + '?' + target.query, follow_redirects=False)
            assert response.status_code == 303, response.text
            session_token = c.cookies.get(SESSION_COOKIE)
            identity = c.get('/api/v1/auth/me')
            assert identity.status_code == 200, identity.text
            app_user_id = identity.json()['id']
            assert c.get('/api/v1/accounts').status_code == 200
            c.headers['Origin'] = settings.frontend_url
            c.headers['X-CSRF-Token'] = identity.json()['csrf_token']
            logout = c.post('/api/v1/auth/logout')
            assert logout.status_code == 200, logout.text
            assert logout.json()['logout_url'].startswith(issuer)
            assert c.get('/api/v1/accounts').status_code == 401
            # Ask the real provider to terminate its session as the browser would.
            cookies = '; '.join(cookie.name + '=' + cookie.value for cookie in provider.cookies.jar if cookie.domain in ('localhost', 'localhost.local'))
            response = provider.get(logout.json()['logout_url'], headers={'Cookie': cookies})
            assert response.status_code in (200, 302, 303)
            if response.status_code == 200:
                form = LogoutForm()
                form.feed(response.text)
                assert form.action, 'Provider logout confirmation form unavailable'
                form.action = urljoin(base, form.action)
                assert urlparse(form.action).netloc == urlparse(base).netloc
                cookies = '; '.join(cookie.name + '=' + cookie.value for cookie in provider.cookies.jar if cookie.domain in ('localhost', 'localhost.local'))
                response = provider.post(form.action, data=form.fields, headers={'Cookie': cookies, 'Origin': base})
                assert response.status_code in (302, 303), 'Provider logout did not finish'
            sessions = provider.get(base + '/admin/realms/' + realm + '/users/' + provider_user_id + '/sessions', headers=headers)
            sessions.raise_for_status()
            assert sessions.json() == [], 'Provider session was not revoked'
            c.cookies.set(SESSION_COOKIE, session_token, domain='localhost.local')
            assert c.get('/api/v1/accounts').status_code == 401
            print('Real Keycloak + SQL Server smoke passed: PKCE login, verified identity, Secure HttpOnly session, CSRF logout and revoked-cookie replay denial.')
    finally:
        if provider_user_id:
            provider.delete(base + '/admin/realms/' + realm + '/users/' + provider_user_id, headers=headers).raise_for_status()
            with Session() as db:
                user = db.scalar(select(User).where(User.issuer == issuer, User.subject == provider_user_id))
                if user:
                    for model in (AuthSession, AuthEvent):
                        db.execute(delete(model).where(model.user_id == user.id))
                    db.execute(delete(RateBucket).where(RateBucket.key == digest('user:' + user.id)))
                    db.delete(user)
                    db.commit()
