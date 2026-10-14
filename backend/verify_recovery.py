"""Actual fresh migrations, backup/restore and schema rollback on synthetic DBs.

Only newly generated PesoPilotQA_/PesoPilotRestore_ databases may be removed.
No application database, real owner or pre-existing backup is touched.
"""
import json
import os
import re
import time
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine, text
from alembic.config import Config
from alembic import command
from app.db import engine

suffix = uuid4().hex[:12]
source, restored = 'PesoPilotQA_' + suffix, 'PesoPilotRestore_' + suffix
backup_dir = Path(__file__).resolve().parent / '.qa-backups'
backup_dir.mkdir(exist_ok=True)
server_backup_dir = os.environ.get('QA_SERVER_BACKUP_DIR', str(backup_dir))
backup = server_backup_dir.rstrip('\\/') + ('/' if server_backup_dir.startswith('/') else '\\') + source + '.bak'
created = []
master = create_engine(engine.url.set(database='master'), isolation_level='AUTOCOMMIT')


def migrate(database, target):
    temporary = create_engine(engine.url.set(database=database))
    try:
        with temporary.begin() as connection:
            config = Config(str(Path(__file__).with_name('alembic.ini')))
            config.set_main_option('script_location', str(Path(__file__).with_name('migrations')))
            config.attributes['connection'] = connection
            if target == '0004':
                command.downgrade(config, target)
            else:
                command.upgrade(config, target)
    finally:
        temporary.dispose()


try:
    with master.connect() as connection:
        assert connection.scalar(text('SELECT DB_ID(:name)'), {'name': source}) is None
        connection.exec_driver_sql(f'CREATE DATABASE [{source}]')
        created.append(source)
    migrate(source, 'head')
    temporary = create_engine(engine.url.set(database=source))
    with temporary.begin() as connection:
        connection.exec_driver_sql("INSERT INTO users (id, issuer, subject, display_name, created_at) VALUES ('synthetic', 'urn:qa', 'synthetic', 'Synthetic', GETUTCDATE())")
        connection.exec_driver_sql("INSERT INTO financial_accounts (user_id, name, kind, opening_minor, currency, archived, version) VALUES ('synthetic', 'Synthetic', 'cash', 0, 'PHP', 0, 1)")
        connection.exec_driver_sql("INSERT INTO transactions (user_id, account_id, occurred_at, description, category, kind, amount_minor, version) SELECT 'synthetic', id, '2026-10-01', 'Synthetic', 'Other', 'expense', 3, 1 FROM financial_accounts")
    temporary.dispose()
    migrate(source, '0004')
    migrate(source, 'head')
    started = time.perf_counter()
    with master.connect() as connection:
        cursor = connection.connection.driver_connection.cursor()
        cursor.execute(f'BACKUP DATABASE [{source}] TO DISK = ? WITH COPY_ONLY, INIT, CHECKSUM', (backup,))
        while cursor.nextset():
            pass
        cursor.close()
        files = connection.exec_driver_sql('RESTORE FILELISTONLY FROM DISK = ?', (backup,)).mappings().all()
        data_path = connection.scalar(text("SELECT CONVERT(nvarchar(4000), SERVERPROPERTY('InstanceDefaultDataPath'))"))
        log_path = connection.scalar(text("SELECT CONVERT(nvarchar(4000), SERVERPROPERTY('InstanceDefaultLogPath'))"))
        assert connection.scalar(text('SELECT DB_ID(:name)'), {'name': restored}) is None
        moves = []
        for item in files:
            logical = item['LogicalName'].replace("'", "''")
            directory = log_path if item['Type'] == 'L' else data_path
            destination = directory.rstrip('\\/') + ('/' if directory.startswith('/') else '\\') + restored + ('_log.ldf' if item['Type'] == 'L' else '.mdf')
            moves.append("MOVE N'" + logical + "' TO N'" + destination.replace("'", "''") + "'")
        created.append(restored)
        cursor = connection.connection.driver_connection.cursor()
        cursor.execute(f'RESTORE DATABASE [{restored}] FROM DISK = ? WITH CHECKSUM, RECOVERY, ' + ', '.join(moves), (backup,))
        while cursor.nextset():
            pass
        cursor.close()
        connection.exec_driver_sql(f'DBCC CHECKDB ([{restored}]) WITH NO_INFOMSGS')
        assert connection.scalar(text(f'SELECT SUM(amount_minor) FROM [{restored}].dbo.transactions')) == 3
        assert connection.scalar(text(f'SELECT version_num FROM [{restored}].dbo.alembic_version')) == '0006'
    print(json.dumps({'fresh_migrations': '0001-0006', 'rollback_reupgrade': '0006-0004-0006', 'restored_centavos': 3, 'restore_ms': round((time.perf_counter() - started) * 1000, 3), 'scope': 'synthetic local databases; production encryption and recovery objectives unverified'}))
finally:
    with master.connect() as connection:
        for database in reversed(created):
            assert re.fullmatch(r'PesoPilot(?:QA|Restore)_[a-f0-9]{12}', database)
            if connection.scalar(text('SELECT DB_ID(:name)'), {'name': database}) is not None:
                connection.exec_driver_sql(f'ALTER DATABASE [{database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE')
                connection.exec_driver_sql(f'DROP DATABASE [{database}]')
    master.dispose()
    backup_path = (backup_dir / (source + '.bak')).resolve()
    assert backup_path.parent == backup_dir.resolve()
    backup_path.unlink(missing_ok=True)
