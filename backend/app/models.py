from datetime import date, datetime
from uuid import uuid4
from sqlalchemy import CheckConstraint, Boolean, BigInteger, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class User(Base):
    __tablename__ = 'users'
    __table_args__ = (UniqueConstraint('issuer', 'subject'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    issuer: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime)

class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)

class LoginFlow(Base):
    __tablename__ = 'login_flows'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)

class AuthEvent(Base):
    __tablename__ = 'auth_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    event: Mapped[str] = mapped_column(String(40))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)

class RateBucket(Base):
    __tablename__ = 'rate_buckets'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)

class Account(Base):
    __tablename__ = 'financial_accounts'
    __table_args__ = (UniqueConstraint('id', 'user_id', name='uq_account_owner'), CheckConstraint('opening_minor >= 0 AND opening_minor <= 100000000000', name='ck_account_opening'), CheckConstraint("kind IN ('cash', 'bank', 'ewallet')", name='ck_account_kind'), CheckConstraint('version >= 1', name='ck_account_version'))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(16))
    opening_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3), default='PHP')
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)

class Transaction(Base):
    __tablename__ = 'transactions'
    __table_args__ = (CheckConstraint('amount_minor > 0 AND amount_minor <= 100000000000', name='ck_transaction_amount'), CheckConstraint("kind IN ('income', 'expense')", name='ck_transaction_kind'), CheckConstraint('version >= 1', name='ck_transaction_version'), Index('ix_transactions_owner_account_page', 'user_id', 'account_id', 'occurred_at', 'id'), Index('ix_transactions_owner_date', 'user_id', 'occurred_at'), ForeignKeyConstraint(['account_id', 'user_id'], ['financial_accounts.id', 'financial_accounts.user_id'], name='fk_transaction_account_owner'))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    account_id: Mapped[int] = mapped_column(ForeignKey('financial_accounts.id'))
    occurred_at: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(16))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    version: Mapped[int] = mapped_column(Integer, default=1)

class Budget(Base):
    __tablename__ = 'budgets'
    __table_args__ = (UniqueConstraint('user_id', 'month', 'category'), CheckConstraint('limit_minor > 0 AND limit_minor <= 100000000000', name='ck_budget_limit'), CheckConstraint('version >= 1', name='ck_budget_version'))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    month: Mapped[str] = mapped_column(String(7))
    category: Mapped[str] = mapped_column(String(40))
    limit_minor: Mapped[int] = mapped_column(BigInteger)
    version: Mapped[int] = mapped_column(Integer, default=1)

class ImportBatch(Base):
    __tablename__ = 'import_batches'
    __table_args__ = (UniqueConstraint('user_id', 'account_id', 'digest'), ForeignKeyConstraint(['account_id', 'user_id'], ['financial_accounts.id', 'financial_accounts.user_id'], name='fk_import_account_owner'))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    account_id: Mapped[int] = mapped_column(ForeignKey('financial_accounts.id'))
    digest: Mapped[str] = mapped_column(String(64))
