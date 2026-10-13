"""OIDC users, revocable sessions, login flows, audit events and rate limits.

Existing demo owners become isolated legacy identities; their data is never
automatically assigned to the first person who signs in.
"""
from datetime import datetime, timezone
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None
OWNED = ('financial_accounts', 'transactions', 'budgets', 'import_batches')

def upgrade():
    op.create_table('users', sa.Column('id', sa.String(36), primary_key=True), sa.Column('issuer', sa.String(255), nullable=False), sa.Column('subject', sa.String(255), nullable=False), sa.Column('display_name', sa.String(160), nullable=False), sa.Column('created_at', sa.DateTime, nullable=False), sa.UniqueConstraint('issuer', 'subject', name='uq_users_identity'))
    connection = op.get_bind()
    owners = set()
    for table in OWNED:
        owners.update(connection.execute(sa.text(f'SELECT DISTINCT user_id FROM {table}')).scalars())
    users = sa.table('users', sa.column('id'), sa.column('issuer'), sa.column('subject'), sa.column('display_name'), sa.column('created_at'))
    for owner in owners:
        connection.execute(users.insert().values(id=owner, issuer='urn:pesopilot:legacy', subject=owner, display_name='Isolated legacy demo', created_at=datetime.now(timezone.utc).replace(tzinfo=None)))
    for table in OWNED:
        op.create_foreign_key(f'fk_{table}_user', table, 'users', ['user_id'], ['id'])
    op.create_unique_constraint('uq_account_owner', 'financial_accounts', ['id', 'user_id'])
    op.create_foreign_key('fk_transaction_account_owner', 'transactions', 'financial_accounts', ['account_id', 'user_id'], ['id', 'user_id'])
    op.create_foreign_key('fk_import_account_owner', 'import_batches', 'financial_accounts', ['account_id', 'user_id'], ['id', 'user_id'])
    op.create_table('auth_sessions', sa.Column('token_hash', sa.String(64), primary_key=True), sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False), sa.Column('csrf_token', sa.String(64), nullable=False), sa.Column('created_at', sa.DateTime, nullable=False), sa.Column('expires_at', sa.DateTime, nullable=False), sa.Column('last_seen_at', sa.DateTime, nullable=False))
    op.create_index('ix_auth_sessions_user_id', 'auth_sessions', ['user_id'])
    op.create_index('ix_auth_sessions_expires_at', 'auth_sessions', ['expires_at'])
    op.create_table('login_flows', sa.Column('token_hash', sa.String(64), primary_key=True), sa.Column('payload', sa.Text, nullable=False), sa.Column('expires_at', sa.DateTime, nullable=False))
    op.create_index('ix_login_flows_expires_at', 'login_flows', ['expires_at'])
    op.create_table('auth_events', sa.Column('id', sa.Integer, primary_key=True), sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=True), sa.Column('event', sa.String(40), nullable=False), sa.Column('occurred_at', sa.DateTime, nullable=False))
    op.create_index('ix_auth_events_occurred_at', 'auth_events', ['occurred_at'])
    op.create_table('rate_buckets', sa.Column('key', sa.String(64), primary_key=True), sa.Column('window', sa.BigInteger, primary_key=True), sa.Column('count', sa.Integer, nullable=False))

def downgrade():
    op.drop_table('rate_buckets')
    op.drop_table('auth_events')
    op.drop_table('login_flows')
    op.drop_table('auth_sessions')
    op.drop_constraint('fk_import_account_owner', 'import_batches', type_='foreignkey')
    op.drop_constraint('fk_transaction_account_owner', 'transactions', type_='foreignkey')
    op.drop_constraint('uq_account_owner', 'financial_accounts', type_='unique')
    for table in OWNED:
        op.drop_constraint(f'fk_{table}_user', table, type_='foreignkey')
    op.drop_table('users')
