import os
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['DEMO_MODE'] = 'true'

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, session, settings
from app.main import app
from app.models import Account, Transaction

@pytest.fixture
def client():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[session] = override
    with factory() as db:
        db.add(Account(user_id='another-owner', name='Private', kind='bank', opening_minor=0))
        db.commit()
    with TestClient(app) as test:
        yield test, factory
    app.dependency_overrides.clear()
    engine.dispose()

def create_account(c):
    result = c.post('/api/v1/accounts', json={'name': 'Demo', 'kind': 'cash'})
    assert result.status_code == 201
    return result.json()['id']

def test_reconciliation_and_budget(client):
    c, _ = client
    account = create_account(c)
    for kind, amount in [('income', '100.00'), ('expense', '0.01'), ('expense', '0.02')]:
        result = c.post('/api/v1/transactions', json={'account_id': account, 'occurred_at': '2026-10-01', 'description': 'Synthetic', 'category': 'Other', 'kind': kind, 'amount': amount})
        assert result.status_code == 201
    assert c.post('/api/v1/budgets', json={'month': '2026-10', 'category': 'Other', 'amount': '0.02'}).status_code == 201
    summary = c.get('/api/v1/analytics/summary?month=2026-10').json()
    assert summary['net_minor'] == 9997
    assert summary['budgets'][0]['spent_minor'] == 3
    assert c.get('/api/v1/accounts').json()[0]['balance_minor'] == 9997
    assert c.get('/api/v1/analytics/summary?month=bad').status_code == 422

def test_owner_isolation_and_fail_closed(client):
    c, factory = client
    assert c.get('/api/v1/accounts').json() == []
    assert c.post('/api/v1/transactions', json={'account_id': 1, 'occurred_at': '2026-10-01', 'description': 'No', 'category': 'Other', 'kind': 'expense', 'amount': '1.00'}).status_code == 404
    with factory() as db:
        t = Transaction(user_id='another-owner', account_id=1, occurred_at=__import__('datetime').date(2026, 10, 1), description='Private', category='Other', kind='expense', amount_minor=100)
        db.add(t)
        db.commit()
        tid = t.id
    assert c.get('/api/v1/transactions').json() == []
    assert c.delete(f'/api/v1/transactions/{tid}').status_code == 404
    previous = settings.demo_mode
    settings.demo_mode = False
    try:
        assert c.get('/api/v1/accounts').status_code == 401
    finally:
        settings.demo_mode = previous

def test_import_atomic_repeat_protection(client):
    c, factory = client
    account = create_account(c)
    content = b'date,description,category,kind,amount\n2026-10-01,Coffee,Food & dining,expense,1.25\n'
    files = {'file': ('sample.csv', content, 'text/csv')}
    preview = c.post('/api/v1/imports/preview', data={'account_id': account}, files=files).json()
    assert c.get('/api/v1/transactions').json() == []
    data = {'account_id': account, 'digest': preview['digest'], 'acknowledge_duplicates': 'true'}
    assert c.post('/api/v1/imports/confirm', data={**data, 'digest': 'wrong'}, files=files).status_code == 409
    assert c.post('/api/v1/imports/confirm', data=data, files=files).status_code == 200
    assert c.post('/api/v1/imports/confirm', data=data, files=files).status_code == 409
    with factory() as db:
        assert len(db.scalars(select(Transaction)).all()) == 1
