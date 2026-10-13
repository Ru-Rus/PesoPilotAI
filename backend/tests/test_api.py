from datetime import date
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models import Transaction
from conftest import sign_in

def create_account(c):
    result = c.post('/api/v1/accounts', json={'name': 'Demo', 'kind': 'cash'})
    assert result.status_code == 201, result.text
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

def test_owner_isolation(client):
    c, factory = client
    assert c.get('/api/v1/accounts').json() == []
    assert c.post('/api/v1/transactions', json={'account_id': 1, 'occurred_at': '2026-10-01', 'description': 'No', 'category': 'Other', 'kind': 'expense', 'amount': '1.00'}).status_code == 404
    with factory() as db:
        t = Transaction(user_id='bob', account_id=1, occurred_at=date(2026, 10, 1), description='Private', category='Other', kind='expense', amount_minor=100)
        db.add(t)
        db.commit()
        tid = t.id
    assert c.get('/api/v1/transactions').json() == []
    assert c.delete(f'/api/v1/transactions/{tid}').status_code == 404
    assert c.get('/api/v1/analytics/summary?month=2026-10').json()['expense_minor'] == 0
    sign_in(c, factory, 'bob')
    assert c.get('/api/v1/accounts').json()[0]['name'] == 'Private'
    assert c.get('/api/v1/transactions').json()[0]['id'] == tid
    assert c.delete(f'/api/v1/transactions/{tid}?version=1').status_code == 204

def test_budget_isolation(client):
    c, factory = client
    body = {'month': '2026-10', 'category': 'Other', 'amount': '12.00'}
    assert c.post('/api/v1/budgets', json=body).status_code == 201
    sign_in(c, factory, 'bob')
    assert c.get('/api/v1/analytics/summary?month=2026-10').json()['budgets'] == []
    assert c.post('/api/v1/budgets', json={**body, 'amount': '99.00'}).status_code == 201
    sign_in(c, factory, 'alice')
    assert c.get('/api/v1/analytics/summary?month=2026-10').json()['budgets'][0]['limit_minor'] == 1200

CSV = b'date,description,category,kind,amount\n2026-10-01,Coffee,Food & dining,expense,1.25\n'
FILES = {'file': ('sample.csv', CSV, 'text/csv')}

def test_import_atomic_repeat_protection(client):
    c, factory = client
    account = create_account(c)
    preview = c.post('/api/v1/imports/preview', data={'account_id': account}, files=FILES).json()
    assert c.get('/api/v1/transactions').json() == []
    data = {'account_id': account, 'digest': preview['digest'], 'acknowledge_duplicates': 'true'}
    assert c.post('/api/v1/imports/confirm', data={**data, 'digest': 'wrong'}, files=FILES).status_code == 409
    assert c.post('/api/v1/imports/confirm', data=data, files=FILES).status_code == 200
    assert c.post('/api/v1/imports/confirm', data=data, files=FILES).status_code == 409
    with factory() as db:
        assert len(db.scalars(select(Transaction)).all()) == 1
    sign_in(c, factory, 'bob')
    assert c.post('/api/v1/imports/preview', data={'account_id': account}, files=FILES).status_code == 404
    assert c.post('/api/v1/imports/confirm', data=data, files=FILES).status_code == 404
    preview = c.post('/api/v1/imports/preview', data={'account_id': 1}, files=FILES).json()
    assert not preview['already_imported']
    assert c.post('/api/v1/imports/confirm', data={**data, 'account_id': 1}, files=FILES).status_code == 200

def test_mass_assignment_denied(client):
    c, _ = client
    assert c.post('/api/v1/accounts', json={'name': 'No', 'kind': 'cash', 'user_id': 'bob'}).status_code == 422

def test_database_enforces_account_owner(client):
    _, factory = client
    with factory() as db:
        db.add(Transaction(user_id='alice', account_id=1, occurred_at=date(2026, 10, 1), description='Invalid ownership', category='Other', kind='expense', amount_minor=100))
        with pytest.raises(IntegrityError):
            db.commit()
