from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .db import session
from .auth import owner, now
from .finance import minor
from .models import Transfer, Refund, Transaction, AuthEvent

router = APIRouter()


class MovementInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    occurred_at: date
    amount: str = Field(max_length=32)
    idempotency_key: UUID


class TransferInput(MovementInput):
    source_id: int = Field(gt=0)
    target_id: int = Field(gt=0)


def finish(db, model, values, user):
    from .main import dump
    from sqlalchemy.exc import IntegrityError
    key = values['idempotency_key']
    previous = db.scalar(select(model).where(model.user_id == user, model.idempotency_key == key))
    if previous:
        if any(getattr(previous, field) != value for field, value in values.items()):
            raise HTTPException(409, 'Idempotency key already used with different values')
        return dump(previous)
    row = model(user_id=user, **values)
    db.add(row)
    db.add(AuthEvent(user_id=user, event='movement_created', occurred_at=now()))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Movement changed concurrently; retry with the same key')
    db.refresh(row)
    return dump(row)


@router.post('/transfers', status_code=201)
def transfer(body: TransferInput, db: Session = Depends(session), user=Depends(owner)):
    from .main import writable_account
    try:
        amount = minor(body.amount)
    except ValueError:
        raise HTTPException(422, 'Invalid peso amount')
    if body.source_id == body.target_id:
        raise HTTPException(422, 'Select two different accounts')
    for identifier in sorted({body.source_id, body.target_id}):
        account = writable_account(db, identifier, user)
        if account.currency != 'PHP':
            raise HTTPException(422, 'Only PHP transfers are supported')
    return finish(db, Transfer, dict(source_id=body.source_id, target_id=body.target_id, occurred_at=body.occurred_at, amount_minor=amount, idempotency_key=str(body.idempotency_key)), user)


@router.post('/transactions/{original_id}/refunds', status_code=201)
def refund(original_id: int, body: MovementInput, db: Session = Depends(session), user=Depends(owner)):
    from .main import transaction_owned, writable_account, dump
    try:
        amount = minor(body.amount)
    except ValueError:
        raise HTTPException(422, 'Invalid peso amount')
    original = transaction_owned(db, original_id, user)
    writable_account(db, original.account_id, user)
    original = db.scalar(select(Transaction).where(Transaction.id == original_id, Transaction.user_id == user).with_hint(Transaction, 'WITH (UPDLOCK, HOLDLOCK)', 'mssql').execution_options(populate_existing=True))
    if not original or original.kind != 'expense':
        raise HTTPException(409, 'Refunds require an existing expense')
    values = dict(original_id=original_id, account_id=original.account_id, occurred_at=body.occurred_at, category=original.category, amount_minor=amount, idempotency_key=str(body.idempotency_key))
    previous = db.scalar(select(Refund).where(Refund.user_id == user, Refund.idempotency_key == str(body.idempotency_key)))
    if previous:
        if any(getattr(previous, field) != value for field, value in values.items()):
            raise HTTPException(409, 'Idempotency key already used with different values')
        return dump(previous)
    total = db.scalar(select(func.coalesce(func.sum(Refund.amount_minor), 0)).where(Refund.original_id == original_id, Refund.user_id == user))
    if total + amount > original.amount_minor or body.occurred_at < original.occurred_at:
        raise HTTPException(409, 'Refund exceeds the expense or predates it')
    return finish(db, Refund, values, user)


@router.get('/transfers')
def transfers(db: Session = Depends(session), user=Depends(owner)):
    from .main import dump
    return [dump(row) for row in db.scalars(select(Transfer).where(Transfer.user_id == user).order_by(Transfer.id.desc()).limit(500))]


@router.get('/refunds')
def refunds(db: Session = Depends(session), user=Depends(owner)):
    from .main import dump
    return [dump(row) for row in db.scalars(select(Refund).where(Refund.user_id == user).order_by(Refund.id.desc()).limit(500))]
