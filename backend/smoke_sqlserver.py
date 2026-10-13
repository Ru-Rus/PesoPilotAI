"""Verify real SQL Server authorization and finance behavior; remove smoke data."""
from datetime import timedelta
from uuid import uuid4
import httpx
from fastapi.responses import Response
from fastapi.testclient import TestClient
from sqlalchemy import delete
from app.auth import SESSION_COOKIE, digest, issue_session, now
from app.db import Session, settings
from app.main import app
from app.models import Account, AuthEvent, AuthSession, Budget, ImportBatch, RateBucket, Transaction, User

users = [str(uuid4()), str(uuid4())]

def sign_in(client, user):
    with Session() as db:
        response = Response()
        issue_session(db, user, response)
    client.cookies.clear()
    client.cookies.extract_cookies(httpx.Response(200, headers=response.headers, request=httpx.Request('GET', client.base_url)))
    result = client.get('/api/v1/auth/me')
    assert result.status_code == 200, result.text
    client.headers['Origin'] = settings.frontend_url
    client.headers['X-CSRF-Token'] = result.json()['csrf_token']

try:
    with Session() as db:
        db.add_all([User(id=user, issuer='urn:pesopilot:smoke', subject=user, display_name='Temporary synthetic smoke user', created_at=now()) for user in users])
        db.commit()
    with TestClient(app, base_url=settings.frontend_url) as c:
        assert c.get('/health/ready').status_code == 200
        assert c.get('/api/v1/accounts').status_code == 401
        sign_in(c, users[0])
        response = c.post('/api/v1/accounts', json={'name': 'Temporary synthetic smoke account', 'kind': 'cash'})
        assert response.status_code == 201, response.text
        account = response.json()['id']
        body = {'account_id': account, 'occurred_at': '2026-10-01', 'description': 'Synthetic income', 'category': 'Income', 'kind': 'income', 'amount': '100.00'}
        response = c.post('/api/v1/transactions', json=body)
        assert response.status_code == 201, response.text
        transaction = response.json()['id']
        content = b'date,description,category,kind,amount\n2026-10-01,Synthetic coffee,Food & dining,expense,0.03\n'
        files = {'file': ('sample.csv', content, 'text/csv')}
        response = c.post('/api/v1/imports/preview', data={'account_id': account}, files=files)
        assert response.status_code == 200, response.text
        data = {'account_id': account, 'digest': response.json()['digest'], 'acknowledge_duplicates': 'true'}
        response = c.post('/api/v1/imports/confirm', data=data, files=files)
        assert response.status_code == 200, response.text
        assert c.post('/api/v1/imports/confirm', data=data, files=files).status_code == 409
        assert c.post('/api/v1/budgets', json={'month': '2026-10', 'category': 'Food & dining', 'amount': '1.00'}).status_code == 201
        summary = c.get('/api/v1/analytics/summary?month=2026-10').json()
        assert summary['net_minor'] == 9997 and summary['budgets'][0]['spent_minor'] == 3
        assert c.get('/api/v1/accounts').json()[0]['balance_minor'] == 9997
        sign_in(c, users[1])
        assert c.get('/api/v1/accounts').json() == []
        assert c.get('/api/v1/transactions').json() == []
        assert c.get('/api/v1/analytics/summary?month=2026-10').json()['budgets'] == []
        assert c.post('/api/v1/transactions', json=body).status_code == 404
        assert c.delete(f'/api/v1/transactions/{transaction}').status_code == 404
        assert c.post('/api/v1/imports/preview', data={'account_id': account}, files=files).status_code == 404
        assert c.post('/api/v1/imports/confirm', data=data, files=files).status_code == 404
        token = c.cookies.get(SESSION_COOKIE)
        with Session() as db:
            db.get(AuthSession, digest(token)).expires_at = now() - timedelta(seconds=1)
            db.commit()
        assert c.get('/api/v1/accounts').status_code == 401
        print('SQL Server smoke passed: cookie sessions, anonymous/cross-user denial, expiry, CSV repeat protection, budgets and exact reconciliation.')
finally:
    with Session() as db:
        for model in (AuthEvent, AuthSession, ImportBatch, Transaction, Budget, Account):
            db.execute(delete(model).where(model.user_id.in_(users)))
        db.execute(delete(RateBucket).where(RateBucket.key.in_([digest('user:' + user) for user in users])))
        db.execute(delete(User).where(User.id.in_(users)))
        db.commit()
