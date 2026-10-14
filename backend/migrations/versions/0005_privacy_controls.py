"""Explicit model processing consent and unlinkable deletion receipts."""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('model_consents', sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('enabled', sa.Boolean(), nullable=False), sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False))
    op.create_table('deletion_receipts', sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('completed_at', sa.DateTime(), nullable=False))


def downgrade():
    op.drop_table('deletion_receipts')
    op.drop_table('model_consents')
