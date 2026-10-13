"""Budget versions, finance constraints and paginated account index.

Existing invalid records make the constraint addition fail; never rewrite them.
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None
CHECKS = (
    ('financial_accounts', 'ck_account_opening', 'opening_minor >= 0 AND opening_minor <= 100000000000'),
    ('financial_accounts', 'ck_account_kind', "kind IN ('cash', 'bank', 'ewallet')"),
    ('financial_accounts', 'ck_account_version', 'version >= 1'),
    ('transactions', 'ck_transaction_amount', 'amount_minor > 0 AND amount_minor <= 100000000000'),
    ('transactions', 'ck_transaction_kind', "kind IN ('income', 'expense')"),
    ('transactions', 'ck_transaction_version', 'version >= 1'),
    ('budgets', 'ck_budget_limit', 'limit_minor > 0 AND limit_minor <= 100000000000'),
    ('budgets', 'ck_budget_version', 'version >= 1'),
)


def upgrade():
    op.add_column('budgets', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    for table, name, condition in CHECKS:
        op.create_check_constraint(name, table, condition)
    op.create_index('ix_transactions_owner_account_page', 'transactions', ['user_id', 'account_id', 'occurred_at', 'id'])


def downgrade():
    op.drop_index('ix_transactions_owner_account_page', table_name='transactions')
    for table, name, _ in reversed(CHECKS):
        op.drop_constraint(name, table, type_='check')
    op.drop_column('budgets', 'version')
