"""Verify role permissions using an isolated SQL user without a login."""
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text
from app.db import engine

principal = 'PesoPilotQA_' + uuid4().hex
with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
    connection.exec_driver_sql(Path(__file__).with_name('security_roles.sql').read_text())
    connection.exec_driver_sql(f'CREATE USER [{principal}] WITHOUT LOGIN')
    try:
        connection.exec_driver_sql(f'ALTER ROLE pesopilot_runtime ADD MEMBER [{principal}]')
        connection.exec_driver_sql(f"EXECUTE AS USER = '{principal}'")
        try:
            for table in ('users', 'auth_sessions', 'transactions', 'budgets', 'model_consents'):
                for permission in ('SELECT', 'INSERT', 'UPDATE', 'DELETE'):
                    assert connection.scalar(text('SELECT HAS_PERMS_BY_NAME(:object, \'OBJECT\', :permission)'), {'object': 'dbo.' + table, 'permission': permission}) == 1, (table, permission)
            assert connection.scalar(text("SELECT HAS_PERMS_BY_NAME('dbo.alembic_version', 'OBJECT', 'UPDATE')")) == 0
            assert connection.scalar(text("SELECT HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CREATE TABLE')")) == 0
        finally:
            connection.exec_driver_sql('REVERT')
        print('SQL Server runtime role passed: explicit DML grants, migration and DDL denied. Existing runtime identity unchanged.')
    finally:
        connection.exec_driver_sql(f'DROP USER [{principal}]')
