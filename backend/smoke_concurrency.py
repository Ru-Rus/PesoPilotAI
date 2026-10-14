"""Real SQL Server races using synthetic users; clean all created records."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Barrier, Event, current_thread
from uuid import uuid4
import httpx
from fastapi.responses import Response
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select, update
from app.auth import digest, issue_session, now
from app.db import Session, engine, settings
from app.main import app, writable_account
from app.models import Account, AuthEvent, AuthSession, Budget, ImportBatch, RateBucket, Transaction, User, Transfer, Refund

user = str(uuid4())


def login(client):
    with Session() as db:
        response = Response()
        issue_session(db, user, response)
    client.cookies.extract_cookies(httpx.Response(200, headers=response.headers, request=httpx.Request('GET', client.base_url)))
    identity = client.get('/api/v1/auth/me')
    assert identity.status_code == 200, identity.text
    client.headers.update({'Origin': settings.frontend_url, 'X-CSRF-Token': identity.json()['csrf_token']})


def race(first, second):
    barrier = Barrier(2)
    def run(fn):
        barrier.wait(timeout=10)
        return fn()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, fn) for fn in (first, second)]
        return sorted(f.result(timeout=20).status_code for f in futures)


try:
    with Session() as db:
        db.add(User(id=user, issuer='urn:pesopilot:race', subject=user, display_name='Synthetic race test', created_at=now()))
        db.commit()
    with TestClient(app, base_url=settings.frontend_url) as a, TestClient(app, base_url=settings.frontend_url) as b:
        login(a)
        login(b)
        response = a.post('/api/v1/accounts', json={'name': 'Synthetic race', 'kind': 'cash'})
        assert response.status_code == 201, response.text
        account = response.json()['id']
        payload = {'account_id': account, 'occurred_at': '2026-10-01', 'description': 'Synthetic', 'category': 'Other', 'kind': 'expense', 'amount': '0.03'}
        transaction = a.post('/api/v1/transactions', json=payload).json()['id']
        edit = {**payload, 'amount': '0.02', 'version': 1}
        assert race(lambda: a.patch(f'/api/v1/transactions/{transaction}', json=edit), lambda: b.patch(f'/api/v1/transactions/{transaction}', json=edit)) == [200, 409]
        budget = {'month': '2026-10', 'category': 'Other', 'amount': '0.03'}
        assert a.post('/api/v1/budgets', json=budget).status_code == 201
        assert race(lambda: a.post('/api/v1/budgets', json={**budget, 'version': 1}), lambda: b.post('/api/v1/budgets', json={**budget, 'version': 1})) == [201, 409]
        content = b'date,description,category,kind,amount\n2026-10-01,Synthetic import,Other,expense,0.01\n'
        files = {'file': ('synthetic.csv', content, 'text/csv')}
        preview = a.post('/api/v1/imports/preview', data={'account_id': account}, files=files).json()
        data = {'account_id': account, 'digest': preview['digest'], 'acknowledge_duplicates': 'true'}
        assert race(lambda: a.post('/api/v1/imports/confirm', data=data, files=files), lambda: b.post('/api/v1/imports/confirm', data=data, files=files)) == [200, 409]
        with Session() as db:
            assert len(db.scalars(select(ImportBatch).where(ImportBatch.user_id == user)).all()) == 1
            assert len(db.scalars(select(Transaction).where(Transaction.user_id == user)).all()) == 2

        refund_payload = {'occurred_at': '2026-10-01', 'amount': '0.02'}
        assert race(lambda: a.post(f'/api/v1/transactions/{transaction}/refunds', json={**refund_payload, 'idempotency_key': str(uuid4())}), lambda: b.post(f'/api/v1/transactions/{transaction}/refunds', json={**refund_payload, 'idempotency_key': str(uuid4())})) == [201, 409]
        target = a.post('/api/v1/accounts', json={'name': 'Synthetic target', 'kind': 'cash'}).json()['id']
        transfer_payload = {'source_id': account, 'target_id': target, 'occurred_at': '2026-10-01', 'amount': '0.01', 'idempotency_key': str(uuid4())}
        assert race(lambda: a.post('/api/v1/transfers', json=transfer_payload), lambda: b.post('/api/v1/transfers', json=transfer_payload)) == [201, 201]
        with Session() as db:
            assert len(db.scalars(select(Transfer).where(Transfer.user_id == user)).all()) == 1

        # Prove the posting request reaches the locking SELECT and waits until
        # the concurrent archive commits, then sees the archived state.
        reached_lock = Event()
        def observe(conn, cursor, statement, parameters, context, executemany):
            if current_thread().name != 'MainThread' and 'UPDLOCK' in statement:
                reached_lock.set()
        event.listen(engine, 'before_cursor_execute', observe)
        try:
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix='archive-race') as pool:
                with Session() as db:
                    writable_account(db, account, user)
                    db.execute(update(Account).where(Account.id == account).values(archived=True, version=Account.version + 1))
                    future = pool.submit(b.post, '/api/v1/transactions', json=payload)
                    assert reached_lock.wait(timeout=10), 'Posting request did not reach account lock'
                    try:
                        future.result(timeout=0.2)
                        raise AssertionError('Write did not wait for archive transaction')
                    except TimeoutError:
                        pass
                    db.commit()
                assert future.result(timeout=10).status_code == 409
        finally:
            event.remove(engine, 'before_cursor_execute', observe)
        print('SQL Server concurrency passed: single edit winner, single budget winner, atomic repeat import, archive/write serialization, bounded competing refunds and idempotent transfers.')
finally:
    with Session() as db:
        for model in (AuthEvent, AuthSession, ImportBatch, Refund, Transfer, Transaction, Budget, Account):
            db.execute(delete(model).where(model.user_id == user))
        db.execute(delete(RateBucket).where(RateBucket.key == digest('user:' + user)))
        db.execute(delete(User).where(User.id == user))
        db.commit()
