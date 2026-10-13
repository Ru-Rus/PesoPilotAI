"""Exercise the real database with temporary synthetic rows, then clean them up."""
from datetime import date
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import delete
from app.db import Session
from app.main import app, owner
from app.models import Account, Budget, ImportBatch, Transaction

user = 'smoke-' + uuid4().hex[:30]
app.dependency_overrides[owner] = lambda: user
try:
    with TestClient(app) as c:
        assert c.get('/health/ready').status_code == 200
        response = c.post('/api/v1/accounts', json={'name': 'Temporary synthetic smoke account', 'kind': 'cash'})
        assert response.status_code == 201, response.text
        account = response.json()['id']
        month = '2026-10'
        response = c.post('/api/v1/transactions', json={'account_id': account, 'occurred_at': month + '-01', 'description': 'Synthetic income', 'category': 'Income', 'kind': 'income', 'amount': '100.00'})
        assert response.status_code == 201, response.text
        content = b'date,description,category,kind,amount\n2026-10-01,Synthetic coffee,Food & dining,expense,0.03\n'
        files = {'file': ('sample.csv', content, 'text/csv')}
        response = c.post('/api/v1/imports/preview', data={'account_id': account}, files=files)
        assert response.status_code == 200, response.text
        data = {'account_id': account, 'digest': response.json()['digest'], 'acknowledge_duplicates': 'true'}
        response = c.post('/api/v1/imports/confirm', data=data, files=files)
        assert response.status_code == 200, response.text
        assert c.post('/api/v1/imports/confirm', data=data, files=files).status_code == 409
        assert c.post('/api/v1/budgets', json={'month': month, 'category': 'Food & dining', 'amount': '1.00'}).status_code == 201
        summary = c.get('/api/v1/analytics/summary?month=' + month).json()
        assert summary['net_minor'] == 9997, summary
        assert summary['budgets'][0]['spent_minor'] == 3
        assert c.get('/api/v1/accounts').json()[0]['balance_minor'] == 9997
        print('SQL Server smoke passed: readiness, account, transaction, CSV preview/confirm/repeat protection, budget, exact reconciliation.')
finally:
    app.dependency_overrides.clear()
    with Session() as db:
        for model in (ImportBatch, Transaction, Budget, Account):
            db.execute(delete(model).where(model.user_id == user))
        db.commit()
