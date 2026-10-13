import hashlib
from datetime import date
from typing import Literal
from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select, text, func, case, update, or_, and_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from .db import session
from .auth import event, now, owner, router as auth_router
from .models import AuthEvent, Account, Transaction, Budget, ImportBatch
from .finance import CATEGORIES, minor, parse_csv

app = FastAPI(title='PesoPilot API', version='0.1.0')
app.include_router(auth_router, prefix='/api/v1/auth')

from .security import install_security
install_security(app)

def account_owned(db, account_id, user, lock=False):
    query = select(Account).where(Account.id == account_id, Account.user_id == user)
    if lock:
        query = query.with_hint(Account, 'WITH (UPDLOCK, HOLDLOCK, ROWLOCK)', dialect_name='mssql').execution_options(populate_existing=True)
    account = db.scalar(query)
    if not account:
        event(db, 'authorization_denied', user)
        raise HTTPException(404, 'Account not found')
    return account

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

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
    amount: str = Field(max_length=32)

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

class AccountEdit(AccountInput):
    version: int = Field(ge=1)
    archived: bool = False

class TransactionEdit(TransactionInput):
    version: int = Field(ge=1)

class BudgetInput(Input):
    version: int | None = Field(default=None, ge=1)
    month: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    category: str
    amount: str = Field(max_length=32)
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
    balances = dict(db.execute(select(Transaction.account_id, func.sum(case((Transaction.kind == 'income', Transaction.amount_minor), else_=-Transaction.amount_minor))).where(Transaction.user_id == user).group_by(Transaction.account_id)).all())
    return [{**dump(a), 'balance_minor': a.opening_minor + balances.get(a.id, 0)} for a in rows]

@app.patch('/api/v1/accounts/{account_id}')
def edit_account(account_id: int, body: AccountEdit, db: Session = Depends(session), user=Depends(owner)):
    account_owned(db, account_id, user, lock=True)
    result = db.execute(update(Account).where(Account.id == account_id, Account.user_id == user, Account.version == body.version).values(**body.model_dump(exclude={'version'}), version=Account.version + 1))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'Account changed; reload before editing')
    db.add(AuthEvent(event='account_updated', user_id=user, occurred_at=now()))
    db.commit()
    return dump(account_owned(db, account_id, user))

@app.post('/api/v1/accounts', status_code=201)
def add_account(body: AccountInput, db: Session = Depends(session), user=Depends(owner)):
    row = Account(user_id=user, **body.model_dump())
    db.add(row)
    db.add(AuthEvent(event='finance_created', user_id=user, occurred_at=now()))
    db.commit()
    db.refresh(row)
    return dump(row)

@app.get('/api/v1/transactions')
def transactions(limit: int = 100, before_date: date | None = None, before_id: int | None = None, account_id: int | None = None, db: Session = Depends(session), user=Depends(owner)):
    if not 1 <= limit <= 500:
        raise HTTPException(422, 'Limit must be 1–500')
    query = select(Transaction).where(Transaction.user_id == user)
    if account_id is not None:
        account_owned(db, account_id, user)
        query = query.where(Transaction.account_id == account_id)
    if (before_date is None) != (before_id is None) or (before_id is not None and before_id < 1):
        raise HTTPException(422, 'Cursor requires a date and positive ID')
    if before_date is not None:
        query = query.where(or_(Transaction.occurred_at < before_date, and_(Transaction.occurred_at == before_date, Transaction.id < before_id)))
    return [dump(t) for t in db.scalars(query.order_by(Transaction.occurred_at.desc(), Transaction.id.desc()).limit(limit))]

def writable_account(db, account_id, user):
    account = account_owned(db, account_id, user, lock=True)
    if account.archived:
        raise HTTPException(409, 'Restore this account before adding or editing entries')
    return account

def transaction_owned(db, transaction_id, user):
    row = db.scalar(select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user))
    if row is None:
        event(db, 'authorization_denied', user)
        raise HTTPException(404, 'Transaction not found')
    return row

@app.patch('/api/v1/transactions/{transaction_id}')
def edit_transaction(transaction_id: int, body: TransactionEdit, db: Session = Depends(session), user=Depends(owner)):
    row = transaction_owned(db, transaction_id, user)
    for account_id in sorted({row.account_id, body.account_id}):
        writable_account(db, account_id, user)
    values = body.model_dump(exclude={'amount', 'version'})
    result = db.execute(update(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user, Transaction.version == body.version).values(**values, amount_minor=minor(body.amount), version=Transaction.version + 1))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'Transaction changed; reload before editing')
    db.add(AuthEvent(event='transaction_updated', user_id=user, occurred_at=now()))
    db.commit()
    return dump(transaction_owned(db, transaction_id, user))

@app.post('/api/v1/transactions', status_code=201)
def add_transaction(body: TransactionInput, db: Session = Depends(session), user=Depends(owner)):
    writable_account(db, body.account_id, user)
    row = Transaction(user_id=user, amount_minor=minor(body.amount), **body.model_dump(exclude={'amount'}))
    db.add(row)
    db.add(AuthEvent(event='finance_created', user_id=user, occurred_at=now()))
    db.commit()
    db.refresh(row)
    return dump(row)

@app.delete('/api/v1/transactions/{transaction_id}', status_code=204)
def delete_transaction(transaction_id: int, version: int | None = None, db: Session = Depends(session), user=Depends(owner)):
    transaction_owned(db, transaction_id, user)
    if version is None:
        raise HTTPException(428, 'Supply the current transaction version before deleting')
    result = db.execute(delete(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user, Transaction.version == version))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'Transaction changed; reload before deleting')
    db.add(AuthEvent(event='transaction_deleted', user_id=user, occurred_at=now()))
    db.commit()

@app.post('/api/v1/budgets', status_code=201)
def save_budget(body: BudgetInput, db: Session = Depends(session), user=Depends(owner)):
    row = db.scalar(select(Budget).where(Budget.user_id == user, Budget.month == body.month, Budget.category == body.category))
    if row is None:
        if body.version is not None:
            raise HTTPException(409, 'Budget no longer exists; reload')
        row = Budget(user_id=user, month=body.month, category=body.category, limit_minor=minor(body.amount))
        db.add(row)
    else:
        if body.version is None:
            raise HTTPException(428, 'Supply the current budget version before updating')
        result = db.execute(update(Budget).where(Budget.id == row.id, Budget.user_id == user, Budget.version == body.version).values(limit_minor=minor(body.amount), version=Budget.version + 1))
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(409, 'Budget changed; reload before editing')
    db.add(AuthEvent(event='budget_saved', user_id=user, occurred_at=now()))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Budget changed concurrently; reload')
    db.refresh(row)
    return dump(row)

@app.get('/api/v1/analytics/summary')
def summary(month: str, db: Session = Depends(session), user=Depends(owner)):
    try:
        start = date.fromisoformat(month + '-01')
        end = date(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1)
    except ValueError:
        raise HTTPException(422, 'Month must be YYYY-MM')
    totals = db.execute(select(Transaction.kind, Transaction.category, func.sum(Transaction.amount_minor)).where(Transaction.user_id == user, Transaction.occurred_at >= start, Transaction.occurred_at < end).group_by(Transaction.kind, Transaction.category)).all()
    income = sum(n for kind, _, n in totals if kind == 'income')
    expense = sum(n for kind, _, n in totals if kind == 'expense')
    categories = {c: 0 for c in CATEGORIES}
    for kind, category, amount in totals:
        if kind == 'expense':
            categories[category] = amount
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
    writable_account(db, account_id, user)
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
    writable_account(db, account_id, user)
    content, rows = await csv_data(file)
    if hashlib.sha256(content).hexdigest() != digest:
        raise HTTPException(409, 'File changed; preview again')
    if not acknowledge_duplicates:
        raise HTTPException(422, 'Review duplicate candidates and explicitly confirm all rows')
    db.add(ImportBatch(user_id=user, account_id=account_id, digest=digest))
    try:
        db.flush()
        db.add_all([Transaction(user_id=user, account_id=account_id, **row) for row in rows])
        db.add(AuthEvent(event='import_confirmed', user_id=user, occurred_at=now()))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'File already imported; no rows added')
    return {'imported': len(rows)}
