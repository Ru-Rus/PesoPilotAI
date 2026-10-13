"""Initial local-demo finance schema."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('financial_accounts', sa.Column('id', sa.Integer, primary_key=True), sa.Column('user_id', sa.String(36), nullable=False), sa.Column('name', sa.String(80), nullable=False), sa.Column('kind', sa.String(16), nullable=False), sa.Column('opening_minor', sa.BigInteger, nullable=False), sa.Column('currency', sa.String(3), nullable=False))
    op.create_index('ix_financial_accounts_user_id', 'financial_accounts', ['user_id'])
    op.create_table('transactions', sa.Column('id', sa.Integer, primary_key=True), sa.Column('user_id', sa.String(36), nullable=False), sa.Column('account_id', sa.Integer, sa.ForeignKey('financial_accounts.id'), nullable=False), sa.Column('occurred_at', sa.Date, nullable=False), sa.Column('description', sa.String(160), nullable=False), sa.Column('category', sa.String(40), nullable=False), sa.Column('kind', sa.String(16), nullable=False), sa.Column('amount_minor', sa.BigInteger, nullable=False))
    op.create_index('ix_transactions_owner_date', 'transactions', ['user_id', 'occurred_at'])
    op.create_table('budgets', sa.Column('id', sa.Integer, primary_key=True), sa.Column('user_id', sa.String(36), nullable=False), sa.Column('month', sa.String(7), nullable=False), sa.Column('category', sa.String(40), nullable=False), sa.Column('limit_minor', sa.BigInteger, nullable=False), sa.UniqueConstraint('user_id', 'month', 'category'))
    op.create_table('import_batches', sa.Column('id', sa.Integer, primary_key=True), sa.Column('user_id', sa.String(36), nullable=False), sa.Column('account_id', sa.Integer, sa.ForeignKey('financial_accounts.id'), nullable=False), sa.Column('digest', sa.String(64), nullable=False), sa.UniqueConstraint('user_id', 'account_id', 'digest'))

def downgrade():
    op.drop_table('import_batches')
    op.drop_table('budgets')
    op.drop_table('transactions')
    op.drop_table('financial_accounts')
