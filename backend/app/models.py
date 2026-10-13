from datetime import date
from sqlalchemy import BigInteger, Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Account(Base):
    __tablename__ = 'financial_accounts'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(16))
    opening_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3), default='PHP')

class Transaction(Base):
    __tablename__ = 'transactions'
    __table_args__ = (Index('ix_transactions_owner_date', 'user_id', 'occurred_at'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36))
    account_id: Mapped[int] = mapped_column(ForeignKey('financial_accounts.id'))
    occurred_at: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(16))
    amount_minor: Mapped[int] = mapped_column(BigInteger)

class Budget(Base):
    __tablename__ = 'budgets'
    __table_args__ = (UniqueConstraint('user_id', 'month', 'category'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36))
    month: Mapped[str] = mapped_column(String(7))
    category: Mapped[str] = mapped_column(String(40))
    limit_minor: Mapped[int] = mapped_column(BigInteger)

class ImportBatch(Base):
    __tablename__ = 'import_batches'
    __table_args__ = (UniqueConstraint('user_id', 'account_id', 'digest'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36))
    account_id: Mapped[int] = mapped_column(ForeignKey('financial_accounts.id'))
    digest: Mapped[str] = mapped_column(String(64))
