"""User-controlled export, consent and transactional application-data deletion."""
from typing import cast
from sqlalchemy.engine import CursorResult
import csv
import io
from datetime import timedelta
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, delete, update
from sqlalchemy.orm import Session
from .auth import authenticated, clear_cookie, digest, now, SESSION_COOKIE, FLOW_COOKIE
from .db import session
from .models import Account, Transaction, Budget, ImportBatch, AuthEvent, AuthSession, User, ModelConsent, DeletionReceipt, RateBucket, Transfer, Refund

router = APIRouter()


def fresh(row):
    if row.created_at < now() - timedelta(minutes=5):
        raise HTTPException(403, 'Sign in again before exporting or deleting your data')


def serialize(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name != 'user_id'}


def spreadsheet_text(value):
    value = str(value)
    if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        return "'" + value
    return value


@router.post('/export')
def export_data(format: Literal['json', 'csv'] = 'json', db: Session = Depends(session), identity=Depends(authenticated)):
    fresh(identity)
    db.connection(execution_options={'isolation_level': 'SERIALIZABLE'})
    payload = {}
    export_models: list[tuple[str, type[Account] | type[Transaction] | type[Budget] | type[ImportBatch] | type[ModelConsent] | type[Transfer] | type[Refund]]] = [('accounts', Account), ('transactions', Transaction), ('budgets', Budget), ('imports', ImportBatch), ('model_consent', ModelConsent), ('transfers', Transfer), ('refunds', Refund)]
    for name, model in export_models:
        rows = db.scalars(select(model).where(model.user_id == identity.user_id).limit(50_001)).all()
        if len(rows) > 50_000:
            raise HTTPException(413, 'Export exceeds the synchronous 50,000-row limit; contact the operator for a verified export')
        payload[name] = [serialize(row) for row in rows]
    db.add(AuthEvent(event='data_exported', user_id=identity.user_id, occurred_at=now()))
    db.commit()
    if format == 'json':
        from fastapi.encoders import jsonable_encoder
        return JSONResponse(jsonable_encoder(payload), headers={'Content-Disposition': 'attachment; filename="pesopilot-data.json"'})
    output = io.StringIO(newline='')
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(['date', 'description', 'category', 'kind', 'amount', 'account_id'])
    for row in payload['transactions']:
        amount = row['amount_minor']
        writer.writerow([row['occurred_at'], spreadsheet_text(row['description']), spreadsheet_text(row['category']), row['kind'], f'{amount // 100}.{amount % 100:02d}', row['account_id']])
    return Response(output.getvalue().encode('utf-8-sig'), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="pesopilot-transactions.csv"'})


class ConsentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool
    version: int = Field(default=0, ge=0)


@router.get('/consent')
def consent(db: Session = Depends(session), identity=Depends(authenticated)):
    row = db.get(ModelConsent, identity.user_id)
    return {'enabled': row.enabled if row else False, 'version': row.version if row else 0, 'scope': 'Configured local model receives only aggregate fact types; raw records and questions stay on this server.'}


@router.put('/consent')
def save_consent(body: ConsentInput, db: Session = Depends(session), identity=Depends(authenticated)):
    from sqlalchemy.exc import IntegrityError
    row = db.get(ModelConsent, identity.user_id)
    if row is None:
        if body.version != 0:
            raise HTTPException(409, 'Consent changed; reload')
        db.add(ModelConsent(user_id=identity.user_id, enabled=body.enabled, updated_at=now(), version=1))
    else:
        result = db.execute(update(ModelConsent).where(ModelConsent.user_id == identity.user_id, ModelConsent.version == body.version).values(enabled=body.enabled, updated_at=now(), version=ModelConsent.version + 1))
        if cast(CursorResult, result).rowcount != 1:
            db.rollback()
            raise HTTPException(409, 'Consent changed; reload')
    db.add(AuthEvent(event='model_consent_changed', user_id=identity.user_id, occurred_at=now()))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Consent changed; reload')
    return consent(db, identity)


class DeleteInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirmation: Literal['DELETE MY DATA']


@router.delete('')
def delete_data(body: DeleteInput, db: Session = Depends(session), identity=Depends(authenticated)):
    fresh(identity)
    # Lock the parent before deleting children: new inserts cannot outlive it.
    user = db.scalar(select(User).where(User.id == identity.user_id).with_hint(User, 'WITH (XLOCK, HOLDLOCK)', 'mssql'))
    if user is None:
        raise HTTPException(404, 'User not found')
    for model in (ModelConsent, AuthEvent, AuthSession, ImportBatch, Refund, Transfer, Transaction, Budget, Account):
        db.execute(delete(model).where(model.user_id == identity.user_id))
    db.execute(delete(RateBucket).where(RateBucket.key == digest('user:' + identity.user_id)))
    db.delete(user)
    receipt = str(uuid4())
    db.add(DeletionReceipt(id=receipt, completed_at=now()))
    db.commit()
    response = JSONResponse({'receipt': receipt, 'status': 'deleted', 'scope': 'Active PesoPilot data and sessions deleted. Your identity-provider account remains; operator backup retention applies.'})
    clear_cookie(response, SESSION_COOKIE)
    clear_cookie(response, FLOW_COOKIE)
    return response
