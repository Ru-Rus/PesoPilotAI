"""Immutable transfers and bounded expense refunds with owner constraints."""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint('uq_transaction_account_owner', 'transactions', ['id', 'account_id', 'user_id'])
    op.create_table('transfers', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False), sa.Column('target_id', sa.Integer(), nullable=False), sa.Column('occurred_at', sa.Date(), nullable=False), sa.Column('amount_minor', sa.BigInteger(), nullable=False), sa.Column('idempotency_key', sa.String(36), nullable=False),
        sa.UniqueConstraint('user_id', 'idempotency_key'), sa.CheckConstraint('source_id <> target_id', name='ck_transfer_accounts'), sa.CheckConstraint('amount_minor > 0 AND amount_minor <= 100000000000', name='ck_transfer_amount'),
        sa.ForeignKeyConstraint(['source_id', 'user_id'], ['financial_accounts.id', 'financial_accounts.user_id'], name='fk_transfer_source_owner'), sa.ForeignKeyConstraint(['target_id', 'user_id'], ['financial_accounts.id', 'financial_accounts.user_id'], name='fk_transfer_target_owner'))
    op.create_index('ix_transfers_user_id', 'transfers', ['user_id'])
    op.create_table('refunds', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False), sa.Column('original_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False), sa.Column('occurred_at', sa.Date(), nullable=False), sa.Column('category', sa.String(40), nullable=False), sa.Column('amount_minor', sa.BigInteger(), nullable=False), sa.Column('idempotency_key', sa.String(36), nullable=False),
        sa.UniqueConstraint('user_id', 'idempotency_key'), sa.CheckConstraint('amount_minor > 0 AND amount_minor <= 100000000000', name='ck_refund_amount'), sa.ForeignKeyConstraint(['original_id', 'account_id', 'user_id'], ['transactions.id', 'transactions.account_id', 'transactions.user_id'], name='fk_refund_original_owner'))
    op.create_index('ix_refunds_user_id', 'refunds', ['user_id'])


def downgrade():
    op.drop_table('refunds')
    op.drop_table('transfers')
    op.drop_constraint('uq_transaction_account_owner', 'transactions', type_='unique')
