import json
from datetime import timedelta
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from app.auth import digest, now, SESSION_COOKIE
from app.db import Settings, session
from app.main import app
from app.models import AuthEvent, AuthSession, ImportBatch, Transaction
from app.finance import minor
from conftest import sign_in
from test_api import create_account, FILES
from test_lifecycle import body


def test_budget_preconditions_and_conflicts(client):
    c, _ = client
    payload = {'month': '2026-10', 'category': 'Other', 'amount': '0.03'}
    assert c.post('/api/v1/budgets', json=payload).json()['version'] == 1
    assert c.post('/api/v1/budgets', json=payload).status_code == 428
    assert c.post('/api/v1/budgets', json={**payload, 'version': 1, 'amount': '0.02'}).json()['version'] == 2
    assert c.post('/api/v1/budgets', json={**payload, 'version': 1}).status_code == 409
    assert c.get('/api/v1/analytics/summary?month=2026-10').json()['budgets'][0]['limit_minor'] == 2


def test_delete_cannot_remove_newer_transaction(client):
    c, _ = client
    account = create_account(c)
    row = c.post('/api/v1/transactions', json=body(account)).json()
    path = f"/api/v1/transactions/{row['id']}"
    assert c.delete(path).status_code == 428
    assert c.patch(path, json={**body(account), 'amount': '0.02', 'version': 1}).status_code == 200
    assert c.delete(path + '?version=1').status_code == 409
    assert c.get('/api/v1/transactions').json()[0]['amount_minor'] == 2
    assert c.delete(path + '?version=2').status_code == 204


def test_cursor_ignores_newer_inserts_between_pages(client):
    c, _ = client
    account = create_account(c)
    original = [c.post('/api/v1/transactions', json=body(account)).json()['id'] for _ in range(3)]
    first = c.get('/api/v1/transactions?limit=2').json()
    c.post('/api/v1/transactions', json=body(account))
    last = first[-1]
    page = c.get(f"/api/v1/transactions?limit=2&before_date={last['occurred_at']}&before_id={last['id']}").json()
    assert [t['id'] for t in first + page] == original[::-1]


def test_session_management_isolation_secrets_and_replay(client):
    c, factory = client
    first_cookie = c.cookies.get(SESSION_COOKIE)
    sign_in(c, factory, 'alice')
    sessions = c.get('/api/v1/auth/sessions').json()
    assert len(sessions) == 2
    assert sum(s['current'] for s in sessions) == 1
    assert first_cookie not in json.dumps(sessions)
    assert 'csrf_token' not in json.dumps(sessions)
    assert c.delete('/api/v1/auth/sessions/' + digest(first_cookie)).status_code == 204
    sign_in(c, factory, 'bob')
    assert c.delete('/api/v1/auth/sessions/' + sessions[0]['id']).status_code == 404
    c.cookies.clear()
    c.cookies.set(SESSION_COOKIE, first_cookie)
    assert c.get('/api/v1/auth/me').status_code == 401


def test_revoke_current_session_and_expired_listing(client):
    c, factory = client
    cookie = c.cookies.get(SESSION_COOKIE)
    with factory() as db:
        db.add(AuthSession(token_hash=digest('expired'), user_id='alice', csrf_token='secret', created_at=now(), expires_at=now() - timedelta(seconds=1), last_seen_at=now()))
        db.commit()
    sessions = c.get('/api/v1/auth/sessions').json()
    assert len(sessions) == 1
    assert c.delete('/api/v1/auth/sessions/' + digest(cookie)).status_code == 204
    assert c.get('/api/v1/auth/me').status_code == 401


def test_session_routes_require_auth_and_csrf(client):
    c, _ = client
    current = c.get('/api/v1/auth/sessions').json()[0]['id']
    c.headers.pop('X-CSRF-Token')
    assert c.delete('/api/v1/auth/sessions/' + current).status_code == 403
    c.cookies.clear()
    assert c.get('/api/v1/auth/sessions').status_code == 401
    assert c.delete('/api/v1/auth/sessions/' + current).status_code == 401


def test_revocation_during_authentication_fails_closed(client, monkeypatch):
    from app import auth
    from sqlalchemy import delete
    c, _ = client
    token_hash = digest(c.cookies.get(SESSION_COOKIE))
    original = auth.rate_limit
    def revoke_before_touch(db, key, limit):
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash))
        db.commit()
        original(db, key, limit)
    monkeypatch.setattr(auth, 'rate_limit', revoke_before_touch)
    assert c.get('/api/v1/accounts').status_code == 401


def test_provider_outage_still_revokes_local_session(client, monkeypatch):
    from app.auth import oauth
    c, _ = client
    async def unavailable():
        raise RuntimeError('synthetic provider outage')
    monkeypatch.setattr(oauth.keycloak, 'load_server_metadata', unavailable)
    response = c.post('/api/v1/auth/logout')
    assert response.status_code == 200 and response.json()['logout_url'] is None
    assert c.get('/api/v1/auth/me').status_code == 401


def test_validation_does_not_echo_financial_input(client):
    c, _ = client
    private = 'PRIVATE_FINANCIAL_VALUE'
    response = c.post('/api/v1/transactions', json={**body(1), 'amount': private})
    assert response.status_code == 422
    assert private not in response.text
    assert response.headers['x-request-id'] == response.json()['request_id']
    assert response.headers['x-frame-options'] == 'DENY'
    assert response.headers['cache-control'] == 'no-store'


def test_body_limit_runs_before_parsing(client):
    c, _ = client
    response = c.post('/api/v1/accounts', content=b'x' * 2_000_001, headers={'Content-Type': 'application/json'})
    assert response.status_code == 413
    assert 'x-request-id' in response.headers
    assert c.post('/api/v1/imports/preview', data={'account_id': 1}, files={'file': ('oversized.csv', b'x' * 2_000_001, 'text/csv')}).status_code == 413


def test_database_failure_response_and_logs_are_safe(client, caplog):
    private = 'PRIVATE_PARAMETER_OR_CONNECTION'
    def broken():
        raise OperationalError('SELECT secret', {'secret': private}, Exception(private))
        yield
    previous = app.dependency_overrides[session]
    app.dependency_overrides[session] = broken
    try:
        response = client[0].get('/health/ready')
        assert response.status_code == 503
        assert private not in response.text and private not in caplog.text
        assert 'SELECT secret' not in caplog.text
    finally:
        app.dependency_overrides[session] = previous


def test_failed_import_rolls_back_batch_rows_and_audit(client, monkeypatch):
    c, factory = client
    account = create_account(c)
    preview = c.post('/api/v1/imports/preview', data={'account_id': account}, files=FILES).json()
    # Fail after the batch INSERT has flushed, during insertion of finance rows.
    from sqlalchemy import event
    engine = factory.kw['bind']
    def reject_rows(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('INSERT INTO TRANSACTIONS'):
            raise IntegrityError(statement, parameters, Exception('synthetic failure'))
    event.listen(engine, 'before_cursor_execute', reject_rows)
    try:
        response = c.post('/api/v1/imports/confirm', data={'account_id': account, 'digest': preview['digest'], 'acknowledge_duplicates': 'true'}, files=FILES)
        assert response.status_code == 409
    finally:
        event.remove(engine, 'before_cursor_execute', reject_rows)
    with factory() as db:
        assert db.scalar(select(ImportBatch)) is None
        assert db.scalar(select(Transaction)) is None
        assert db.scalar(select(AuthEvent).where(AuthEvent.event == 'import_confirmed')) is None
    assert c.post('/api/v1/imports/confirm', data={'account_id': account, 'digest': preview['digest'], 'acknowledge_duplicates': 'true'}, files=FILES).status_code == 200


@pytest.mark.parametrize('kind,amount', [('transfer', 1), ('expense', -1), ('income', 0), ('expense', 100000000001)])
def test_database_finance_constraints(client, kind, amount):
    c, factory = client
    account = create_account(c)
    with factory() as db:
        from datetime import date
        db.add(Transaction(user_id='alice', account_id=account, occurred_at=date(2026, 10, 1), description='Synthetic', category='Other', kind=kind, amount_minor=amount))
        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.parametrize('value', ['1e2', '1.000', '9' * 10000, '0.000000000000000000000000001', '+1', '1_000'])
def test_bounded_amount_grammar(value):
    with pytest.raises(ValueError):
        minor(value)


def production(**overrides):
    return Settings(_env_file=None, app_env='production', oidc_client_secret='test-only', oidc_issuer='https://identity.example/realm', database_url=overrides.pop('database_url', 'mssql+pyodbc://localhost/PesoPilot?Encrypt=yes&TrustServerCertificate=no'), **overrides)


def test_production_transport_guards():
    assert production().app_env == 'production'
    for url in ('sqlite://', 'mssql+pyodbc://localhost/PesoPilot?Encrypt=no&TrustServerCertificate=no', 'mssql+pyodbc://localhost/PesoPilot?Encrypt=yes&TrustServerCertificate=yes'):
        with pytest.raises(ValidationError):
            production(database_url=url)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env='production', oidc_client_secret='test-only')
