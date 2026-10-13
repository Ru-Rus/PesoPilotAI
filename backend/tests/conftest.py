import os
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['OIDC_CLIENT_SECRET'] = 'test-only-client-secret'

import pytest
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.responses import Response
from app.auth import SESSION_COOKIE, issue_session, now
from app.db import Base, session, settings
from app.main import app
from app.models import Account, User

@pytest.fixture
def client():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[session] = override
    with factory() as db:
        db.add_all([User(id=name, issuer=settings.oidc_issuer, subject=name, display_name=name.title(), created_at=now()) for name in ('alice', 'bob')])
        db.commit()
        db.add(Account(user_id='bob', name='Private', kind='bank', opening_minor=0))
        db.commit()
    with TestClient(app, base_url=settings.frontend_url) as test:
        sign_in(test, factory, 'alice')
        yield test, factory
    app.dependency_overrides.clear()
    engine.dispose()

def sign_in(client, factory, user):
    with factory() as db:
        response = Response()
        issue_session(db, user, response)
        cookie = response.headers['set-cookie'].split(';')[0].split('=', 1)[1]
    client.cookies.clear()
    client.cookies.extract_cookies(httpx.Response(200, headers=response.headers, request=httpx.Request('GET', client.base_url)))
    me = client.get('/api/v1/auth/me')
    assert me.status_code == 200, me.text
    client.headers['Origin'] = settings.frontend_url
    client.headers['X-CSRF-Token'] = me.json()['csrf_token']
    return cookie
