from uuid import uuid4
from conftest import sign_in
from test_api import create_account
from test_lifecycle import body


def test_transfer_is_idempotent_and_excluded_from_cashflow(client):
    c, factory = client
    source, target = create_account(c), create_account(c)
    payload = {'source_id': source, 'target_id': target, 'occurred_at': '2026-10-01', 'amount': '0.03', 'idempotency_key': str(uuid4())}
    first = c.post('/api/v1/transfers', json=payload)
    assert first.status_code == 201
    assert c.post('/api/v1/transfers', json=payload).json()['id'] == first.json()['id']
    assert c.post('/api/v1/transfers', json={**payload, 'amount': '0.02'}).status_code == 409
    balances = {a['id']: a['balance_minor'] for a in c.get('/api/v1/accounts').json()}
    assert balances[source] == -3 and balances[target] == 3 and sum(balances.values()) == 0
    assert c.get('/api/v1/analytics/summary?month=2026-10').json()['net_minor'] == 0
    assert c.get('/api/v1/ai/insights?month=2026-10').json()['expense_minor'] == 0
    assert c.post('/api/v1/me/export').json()['transfers'][0]['amount_minor'] == 3
    sign_in(c, factory, 'bob')
    assert c.get('/api/v1/transfers').json() == []
    assert c.post('/api/v1/transfers', json=payload).status_code == 404


def test_refund_reconciles_and_prevents_overrefund_or_mutation(client):
    c, _ = client
    account = create_account(c)
    row = c.post('/api/v1/transactions', json=body(account)).json()
    path = f"/api/v1/transactions/{row['id']}/refunds"
    payload = {'occurred_at': '2026-10-01', 'amount': '0.02', 'idempotency_key': str(uuid4())}
    first = c.post(path, json=payload)
    assert first.status_code == 201
    assert c.post(path, json=payload).json()['id'] == first.json()['id']
    assert c.post(path, json={**payload, 'idempotency_key': str(uuid4())}).status_code == 409
    assert c.post(path, json={**payload, 'occurred_at': '2026-09-01', 'idempotency_key': str(uuid4())}).status_code == 409
    assert c.get('/api/v1/accounts').json()[0]['balance_minor'] == -1
    assert c.get('/api/v1/analytics/summary?month=2026-10').json()['expense_minor'] == 1
    assert c.get('/api/v1/ai/insights?month=2026-10').json()['expense_minor'] == 1
    assert c.patch(f"/api/v1/transactions/{row['id']}", json={**body(account), 'version': 1, 'amount': '0.01'}).status_code == 409
    assert c.delete(f"/api/v1/transactions/{row['id']}?version=1").status_code == 409
    assert c.get('/api/v1/refunds').json()[0]['amount_minor'] == 2


def test_movement_validation_and_csrf(client):
    c, _ = client
    account = create_account(c)
    payload = {'source_id': account, 'target_id': account, 'occurred_at': '2026-10-01', 'amount': '0.03', 'idempotency_key': str(uuid4())}
    assert c.post('/api/v1/transfers', json=payload).status_code == 422
    assert c.post('/api/v1/transfers', json={**payload, 'target_id': 99999, 'amount': 'NaN'}).status_code == 422
    c.headers.pop('X-CSRF-Token')
    assert c.post('/api/v1/transfers', json=payload).status_code == 403
    c.cookies.clear()
    assert c.get('/api/v1/refunds').status_code == 401
