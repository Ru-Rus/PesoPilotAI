import hashlib
from datetime import date
from typing import Literal
from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from .db import session
from .auth import event, owner, router as auth_router
from .models import Account, Transaction, Budget, ImportBatch
from .finance import CATEGORIES, minor, parse_csv

app = FastAPI(title='PesoPilot API', version='0.1.0')
app.include_router(auth_router, prefix='/api/v1/auth')

@app.middleware('http')
async def privacy_headers(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

def account_owned(db, account_id, user):
    account = db.scalar(select(Account).where(Account.id == account_id, Account.user_id == user))
    if not account:
        event(db, 'authorization_denied', user)
        raise HTTPException(404, 'Account not found')
    return account

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')

class AccountInput(Input):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal['cash', 'bank', 'ewallet']
    opening_minor: int = Field(default=0, ge=0, le=100_000_000_000)

class TransactionInput(Input):
    account_id: int = Field(gt=0)
    occurred_at: date
    description: str = Field(min_length=1, max_length=160)
    category: str
    kind: Literal['income', 'expense']
    amount: str

    @field_validator('category')
    @classmethod
    def category_valid(cls, value):
        if value not in CATEGORIES:
            raise ValueError('Unknown category')
        return value

    @field_validator('amount')
    @classmethod
    def amount_valid(cls, value):
        minor(value)
        return value

class BudgetInput(Input):
    month: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    category: str
    amount: str
    _category = field_validator('category')(TransactionInput.category_valid.__func__)
    _amount = field_validator('amount')(TransactionInput.amount_valid.__func__)

def dump(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns if column.name != 'user_id'}

@app.get('/health/live')
def live():
    return {'status': 'ok'}

@app.get('/health/ready')
def ready(db: Session = Depends(session)):
    try:
        db.execute(text('SELECT 1'))
        return {'status': 'ready'}
    except SQLAlchemyError:
        raise HTTPException(503, 'Database unavailable')

@app.get('/api/v1/accounts')
def accounts(db: Session = Depends(session), user=Depends(owner)):
    rows = db.scalars(select(Account).where(Account.user_id == user)).all()
    tx = db.scalars(select(Transaction).where(Transaction.user_id == user)).all()
    return [{**dump(a), 'balance_minor': a.opening_minor + sum(t.amount_minor if t.kind == 'income' else -t.amount_minor for t in tx if t.account_id == a.id)} for a in rows]

@app.post('/api/v1/accounts', status_code=201)
def add_account(body: AccountInput, db: Session = Depends(session), user=Depends(owner)):
    row = Account(user_id=user, **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return dump(row)

@app.get('/api/v1/transactions')
def transactions(limit: int = 100, db: Session = Depends(session), user=Depends(owner)):
    if not 1 <= limit <= 500:
        raise HTTPException(422, 'Limit must be 1–500')
    return [dump(t) for t in db.scalars(select(Transaction).where(Transaction.user_id == user).order_by(Transaction.occurred_at.desc(), Transaction.id.desc()).limit(limit))]

@app.post('/api/v1/transactions', status_code=201)
def add_transaction(body: TransactionInput, db: Session = Depends(session), user=Depends(owner)):
    account_owned(db, body.account_id, user)
    row = Transaction(user_id=user, amount_minor=minor(body.amount), **body.model_dump(exclude={'amount'}))
    db.add(row)
    db.commit()
    db.refresh(row)
    return dump(row)

@app.delete('/api/v1/transactions/{transaction_id}', status_code=204)
def delete_transaction(transaction_id: int, db: Session = Depends(session), user=Depends(owner)):
    row = db.scalar(select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user))
    if row is None:
        event(db, 'authorization_denied', user)
        raise HTTPException(404, 'Transaction not found')
    db.delete(row)
    db.commit()

@app.post('/api/v1/budgets', status_code=201)
def save_budget(body: BudgetInput, db: Session = Depends(session), user=Depends(owner)):
    row = db.scalar(select(Budget).where(Budget.user_id == user, Budget.month == body.month, Budget.category == body.category))
    if row is None:
        row = Budget(user_id=user, month=body.month, category=body.category)
        db.add(row)
    row.limit_minor = minor(body.amount)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Budget changed concurrently; retry')
    db.refresh(row)
    return dump(row)

@app.get('/api/v1/analytics/summary')
def summary(month: str, db: Session = Depends(session), user=Depends(owner)):
    try:
        start = date.fromisoformat(month + '-01')
        end = date(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1)
    except ValueError:
        raise HTTPException(422, 'Month must be YYYY-MM')
    rows = db.scalars(select(Transaction).where(Transaction.user_id == user, Transaction.occurred_at >= start, Transaction.occurred_at < end)).all()
    income = sum(t.amount_minor for t in rows if t.kind == 'income')
    expense = sum(t.amount_minor for t in rows if t.kind == 'expense')
    categories = {c: sum(t.amount_minor for t in rows if t.category == c and t.kind == 'expense') for c in CATEGORIES}
    budgets = db.scalars(select(Budget).where(Budget.user_id == user, Budget.month == month)).all()
    return {'income_minor': income, 'expense_minor': expense, 'net_minor': income - expense, 'categories': categories, 'budgets': [{**dump(b), 'spent_minor': categories[b.category]} for b in budgets]}

async def csv_data(file):
    content = await file.read(1_000_001)
    try:
        return content, parse_csv(content)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

@app.post('/api/v1/imports/preview')
async def preview(account_id: int = Form(...), file: UploadFile = File(...), db: Session = Depends(session), user=Depends(owner)):
    account_owned(db, account_id, user)
    content, rows = await csv_data(file)
    digest = hashlib.sha256(content).hexdigest()
    imported = db.scalar(select(ImportBatch).where(ImportBatch.user_id == user, ImportBatch.account_id == account_id, ImportBatch.digest == digest))
    existing = db.scalars(select(Transaction).where(Transaction.user_id == user, Transaction.account_id == account_id)).all()
    keys = {(t.occurred_at, t.description, t.category, t.kind, t.amount_minor) for t in existing}
    duplicates = 0
    for row in rows:
        key = tuple(row[k] for k in ('occurred_at', 'description', 'category', 'kind', 'amount_minor'))
        duplicates += key in keys
        keys.add(key)
    return {'digest': digest, 'already_imported': imported is not None, 'duplicate_candidates': duplicates, 'count': len(rows), 'rows': rows[:20]}

@app.post('/api/v1/imports/confirm')
async def confirm(account_id: int = Form(...), digest: str = Form(...), acknowledge_duplicates: bool = Form(False), file: UploadFile = File(...), db: Session = Depends(session), user=Depends(owner)):
    account_owned(db, account_id, user)
    content, rows = await csv_data(file)
    if hashlib.sha256(content).hexdigest() != digest:
        raise HTTPException(409, 'File changed; preview again')
    if not acknowledge_duplicates:
        raise HTTPException(422, 'Review duplicate candidates and explicitly confirm all rows')
    db.add(ImportBatch(user_id=user, account_id=account_id, digest=digest))
    try:
        db.flush()
        db.add_all([Transaction(user_id=user, account_id=account_id, **row) for row in rows])
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'File already imported; no rows added')
    return {'imported': len(rows)}
