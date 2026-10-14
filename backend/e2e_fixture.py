"""Create/clean synthetic provider users for real browser tests; no auth bypass."""
import json
import secrets
import sys
from pathlib import Path
from datetime import timedelta
from uuid import uuid4
import httpx
from dotenv import dotenv_values
from sqlalchemy import delete, select, update
from app.db import settings, Session
from app.auth import now, digest
from app.models import User, ModelConsent, AuthEvent, AuthSession, ImportBatch, Transaction, Budget, Account, RateBucket, DeletionReceipt, Transfer, Refund

fixture = Path(__file__).resolve().parent.parent / 'frontend/.e2e-fixture.json'
base, realm = settings.oidc_issuer.split('/realms/')
config = dotenv_values(Path(__file__).with_name('.env'))


def admin(client):
    response = client.post(base + '/realms/master/protocol/openid-connect/token', data={'grant_type': 'password', 'client_id': 'admin-cli',
        'username': 'admin', 'password': config.get('KEYCLOAK_ADMIN_PASSWORD')})
    response.raise_for_status()
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def cleanup(data):
    with httpx.Client(timeout=20) as client:
        headers = admin(client)
        for item in data['users']:
            result = client.get(base + '/admin/realms/' + realm + '/users', headers=headers, params={'username': item['username'], 'exact': 'true'})
            result.raise_for_status()
            for provider_user in result.json():
                with Session() as db:
                    user = db.scalar(select(User).where(User.issuer == settings.oidc_issuer, User.subject == provider_user['id']))
                    if user:
                        for model in (ModelConsent, AuthEvent, AuthSession, ImportBatch, Refund, Transfer, Transaction, Budget, Account):
                            db.execute(delete(model).where(model.user_id == user.id))
                        db.execute(delete(RateBucket).where(RateBucket.key.in_([digest(prefix + user.id) for prefix in ('user:', 'ai:')])))
                        db.delete(user)
                        db.commit()
                client.delete(base + '/admin/realms/' + realm + '/users/' + provider_user['id'], headers=headers).raise_for_status()
    with Session() as db:
        if data.get('receipts'):
            db.execute(delete(DeletionReceipt).where(DeletionReceipt.id.in_(data['receipts'])))
        db.commit()


if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'setup':
        if fixture.exists():
            cleanup(json.loads(fixture.read_text()))
        data = {'users': [{'username': 'e2e-' + uuid4().hex, 'password': secrets.token_urlsafe(24)} for _ in range(3)], 'receipts': []}
        fixture.write_text(json.dumps(data))
        try:
            with httpx.Client(timeout=20) as client:
                headers = admin(client)
                for user in data['users'][:2]:
                    response = client.post(base + '/admin/realms/' + realm + '/users', headers=headers, json={'username': user['username'], 'enabled': True,
                        'firstName': 'Synthetic', 'lastName': 'Browser', 'email': user['username'] + '@example.invalid', 'credentials': [{'type': 'password', 'value': user['password'], 'temporary': False}]})
                    response.raise_for_status()
            print('Synthetic browser users created; credentials remain in the ignored fixture.')
        except Exception:
            cleanup(data)
            fixture.unlink(missing_ok=True)
            raise
    elif action == 'cleanup':
        if fixture.exists():
            cleanup(json.loads(fixture.read_text()))
            fixture.unlink()
        print('Synthetic browser records removed.')
    elif action == 'expire':
        data = json.loads(fixture.read_text())
        username = data['users'][int(sys.argv[2])]['username']
        with httpx.Client(timeout=20) as client:
            headers = admin(client)
            users = client.get(base + '/admin/realms/' + realm + '/users', headers=headers, params={'username': username, 'exact': 'true'}).json()
        with Session() as db:
            user = db.scalar(select(User).where(User.issuer == settings.oidc_issuer, User.subject == users[0]['id']))
            db.execute(update(AuthSession).where(AuthSession.user_id == user.id).values(expires_at=now() - timedelta(seconds=1)))
            db.commit()
    elif action == 'seed':
        from datetime import date
        data = json.loads(fixture.read_text())
        with httpx.Client(timeout=20) as client:
            headers = admin(client)
            provider = client.get(base + '/admin/realms/' + realm + '/users', headers=headers, params={'username': data['users'][0]['username'], 'exact': 'true'}).json()[0]
        with Session() as db:
            user = db.scalar(select(User).where(User.issuer == settings.oidc_issuer, User.subject == provider['id']))
            account = db.scalar(select(Account).where(Account.user_id == user.id))
            for i in range(105):
                db.add(Transaction(user_id=user.id, account_id=account.id, occurred_at=date(2026, 9, 1), description=f'Synthetic older {i}', category='Other', kind='expense', amount_minor=1))
            db.commit()
