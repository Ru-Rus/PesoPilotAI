from conftest import sign_in
from test_api import create_account, FILES


def body(account):
    return dict(account_id=account, occurred_at='2026-10-01', description='Coffee', category='Other', kind='expense', amount='0.03')


def test_account_archive_restore_and_stale_edit(client):
    c, factory = client
    account = create_account(c)
    edit = dict(name='Renamed', kind='cash', opening_minor=100, archived=True, version=1)
    assert c.patch(f'/api/v1/accounts/{account}', json=edit).json()['version'] == 2
    assert c.patch(f'/api/v1/accounts/{account}', json=edit).status_code == 409
    assert c.post('/api/v1/transactions', json=body(account)).status_code == 409
    assert c.post('/api/v1/imports/preview', data={'account_id': account}, files=FILES).status_code == 409
    assert c.post('/api/v1/imports/confirm', data={'account_id': account, 'digest': 'bad'}, files=FILES).status_code == 409
    assert c.get('/api/v1/accounts').json()[0]['balance_minor'] == 100
    assert c.patch(f'/api/v1/accounts/{account}', json={**edit, 'version': 2, 'archived': False}).status_code == 200
    assert c.post('/api/v1/transactions', json=body(account)).status_code == 201
    sign_in(c, factory, 'bob')
    assert c.patch(f'/api/v1/accounts/{account}', json=edit).status_code == 404


def test_transaction_edit_reconciles_and_rejects_stale_cross_owner(client):
    c, factory = client
    account = create_account(c)
    row = c.post('/api/v1/transactions', json=body(account)).json()
    edit = {**body(account), 'amount': '0.01', 'version': 1}
    assert c.patch(f"/api/v1/transactions/{row['id']}", json=edit).json()['version'] == 2
    assert c.patch(f"/api/v1/transactions/{row['id']}", json=edit).status_code == 409
    assert c.get('/api/v1/analytics/summary?month=2026-10').json()['expense_minor'] == 1
    assert c.get('/api/v1/accounts').json()[0]['balance_minor'] == -1
    assert c.patch(f"/api/v1/transactions/{row['id']}", json={**edit, 'account_id': 1, 'version': 2}).status_code == 404
    sign_in(c, factory, 'bob')
    assert c.patch(f"/api/v1/transactions/{row['id']}", json=edit).status_code == 404


def test_cursor_ties_filters_and_validation(client):
    c, _ = client
    account = create_account(c)
    ids = [c.post('/api/v1/transactions', json=body(account)).json()['id'] for _ in range(3)]
    first = c.get('/api/v1/transactions?limit=2').json()
    assert [t['id'] for t in first] == ids[::-1][:2]
    last = first[-1]
    page = c.get(f"/api/v1/transactions?limit=2&before_date={last['occurred_at']}&before_id={last['id']}").json()
    assert [t['id'] for t in page] == ids[:1]
    assert c.get('/api/v1/transactions?before_id=1').status_code == 422
    assert c.get('/api/v1/transactions?account_id=1').status_code == 404
    assert c.post('/api/v1/accounts', json={'name': '   ', 'kind': 'cash'}).status_code == 422


def test_new_routes_require_session_and_csrf(client):
    c, factory = client
    account = create_account(c)
    row = c.post('/api/v1/transactions', json=body(account)).json()
    c.headers.pop('X-CSRF-Token')
    for path, payload in [(f'/accounts/{account}', dict(name='No', kind='cash', version=1)), (f"/transactions/{row['id']}", {**body(account), 'version': 1})]:
        assert c.patch('/api/v1' + path, json=payload).status_code == 403
        c.cookies.clear()
        assert c.patch('/api/v1' + path, json=payload).status_code == 401
        sign_in(c, factory, 'alice')
        c.headers.pop('X-CSRF-Token')
