"""Measured synthetic SQL Server API/load checks; never seed a real owner."""
import json
import time
import platform
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import httpx
from fastapi.responses import Response
from fastapi.testclient import TestClient
from sqlalchemy import delete, insert, select, func
from app.db import Session, settings
from app.auth import now, issue_session, digest
from app.main import app
from app.models import User, Account, Transaction, AuthEvent, AuthSession, Budget, ImportBatch, RateBucket

users = [str(uuid4()), str(uuid4())]
report = {'platform': platform.system(), 'python': platform.python_version(), 'history_rows': 20000, 'csv_rows': 5000}


def login(client, user):
    with Session() as db:
        response = Response()
        issue_session(db, user, response)
    client.cookies.extract_cookies(httpx.Response(200, headers=response.headers, request=httpx.Request('GET', client.base_url)))
    me = client.get('/api/v1/auth/me')
    assert me.status_code == 200
    client.headers.update({'Origin': settings.frontend_url, 'X-CSRF-Token': me.json()['csrf_token']})


try:
    with Session() as db:
        db.add_all([User(id=u, issuer='urn:pesopilot:scale', subject=u, display_name='Synthetic scale', created_at=now()) for u in users])
        db.commit()
        accounts = [Account(user_id=u, name='Synthetic scale', kind='cash', opening_minor=0) for u in users]
        db.add_all(accounts)
        db.commit()
        ids = [a.id for a in accounts]
        rows = [dict(user_id=users[0], account_id=ids[0], occurred_at=date(2026, 10, 1), description='Synthetic scale', category='Other', kind='expense', amount_minor=1, version=1) for _ in range(20000)]
        for offset in range(0, len(rows), 500):
            db.execute(insert(Transaction), rows[offset:offset + 500])
        db.commit()
    with TestClient(app, base_url=settings.frontend_url) as a, TestClient(app, base_url=settings.frontend_url) as b:
        login(a, users[0]); login(b, users[1])
        timings = []
        for _ in range(25):
            started = time.perf_counter()
            response = a.get('/api/v1/analytics/summary?month=2026-10')
            timings.append((time.perf_counter() - started) * 1000)
            assert response.status_code == 200 and response.json()['expense_minor'] == 20000
        report['summary_p95_ms'] = round(sorted(timings)[23], 3)
        report['summary_p95_target_ms'] = 500
        assert report['summary_p95_ms'] < 500, report
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = [pool.submit(client.get, '/api/v1/analytics/summary?month=2026-10') for client in (a, b)]
            assert [r.result().json()['expense_minor'] for r in responses] == [20000, 0]
        content = ('date,description,category,kind,amount\n' + '2026-10-01,Synthetic CSV,Other,expense,0.01\n' * 5000).encode()
        files = {'file': ('synthetic.csv', content, 'text/csv')}
        started = time.perf_counter()
        preview = b.post('/api/v1/imports/preview', data={'account_id': ids[1]}, files=files)
        assert preview.status_code == 200 and preview.json()['count'] == 5000
        response = b.post('/api/v1/imports/confirm', data={'account_id': ids[1], 'digest': preview.json()['digest'], 'acknowledge_duplicates': 'true'}, files=files)
        report['preview_and_import_ms'] = round((time.perf_counter() - started) * 1000, 3)
        assert response.status_code == 200 and response.json()['imported'] == 5000
        assert report['preview_and_import_ms'] < 60000
        with Session() as db:
            assert db.scalar(select(func.count()).select_from(Transaction).where(Transaction.user_id == users[1])) == 5000
        # Inspect the actual SQL Server plan for the owner/account cursor access path.
        with Session() as db:
            connection = db.connection()
            cursor = connection.connection.driver_connection.cursor()
            cursor.execute('SET SHOWPLAN_XML ON')
            try:
                cursor.execute(f"SELECT TOP 100 id FROM dbo.transactions WHERE user_id = '{users[0]}' AND account_id = {ids[0]} ORDER BY occurred_at DESC, id DESC")
                while cursor.description is None:
                    assert cursor.nextset(), 'SQL Server did not return a query plan'
                plan = cursor.fetchone()[0]
                report['cursor_plan_uses_owner_index'] = 'ix_transactions_owner_account_page' in plan
            finally:
                cursor.execute('SET SHOWPLAN_XML OFF')
                cursor.close()
        assert report['cursor_plan_uses_owner_index']
        print(json.dumps(report))
finally:
    with Session() as db:
        for model in (AuthEvent, AuthSession, ImportBatch, Transaction, Budget, Account):
            db.execute(delete(model).where(model.user_id.in_(users)))
        db.execute(delete(RateBucket).where(RateBucket.key.in_([digest('user:' + user) for user in users])))
        db.execute(delete(User).where(User.id.in_(users)))
        db.commit()
