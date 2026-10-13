"""Account archive state and optimistic edit versions; preserve existing data."""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('financial_accounts', sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.false()))
    for table in ('financial_accounts', 'transactions'):
        op.add_column(table, sa.Column('version', sa.Integer(), nullable=False, server_default='1'))


def downgrade():
    for table in ('transactions', 'financial_accounts'):
        op.drop_column(table, 'version')
    op.drop_column('financial_accounts', 'archived')
