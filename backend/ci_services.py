"""Ephemeral CI infrastructure with generated secrets and labeled cleanup."""
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4
import httpx

root = Path(__file__).resolve().parent.parent
directory = root / '.tools/ci'
state_path = directory / 'services.json'


def docker(*arguments):
    return subprocess.check_output(['docker', *arguments], text=True).strip()


def cleanup():
    if not state_path.exists():
        return
    state = json.loads(state_path.read_text())
    for identifier in state['containers']:
        try:
            label = docker('inspect', '--format', '{{index .Config.Labels "pesopilot.qa.run"}}', identifier)
            if label != state['run']:
                raise RuntimeError('Refusing to remove an unowned container')
            docker('rm', '-f', identifier)
        except subprocess.CalledProcessError:
            continue
    state_path.unlink()


def start():
    import pyodbc
    if (root / 'backend/.env').exists():
        raise RuntimeError('CI setup requires a clean checkout; existing .env is never overwritten')
    directory.mkdir(parents=True, exist_ok=True)
    state = {'run': uuid4().hex, 'containers': []}
    state_path.write_text(json.dumps(state))
    sql_password = 'Q1!' + secrets.token_urlsafe(32)  # pragma: allowlist secret -- generated credential prefix or public environment variable
    admin_password, client_secret = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    values = [sql_password, admin_password, client_secret]
    for value in values:
        if os.environ.get('GITHUB_ACTIONS'):
            print('::add-mask::' + value)
    realm = json.loads((root / 'backend/keycloak/realm.json').read_text())
    realm['clients'][0]['secret'] = client_secret
    (directory / 'realm.json').write_text(json.dumps(realm))
    for filename, content in [('sql.env', 'MSSQL_SA_PASSWORD=' + sql_password), ('keycloak.env', 'KC_BOOTSTRAP_ADMIN_USERNAME=admin\nKC_BOOTSTRAP_ADMIN_PASSWORD=' + admin_password)]:
        (directory / filename).write_text(content)
        (directory / filename).chmod(0o600)
    backup_dir = root / 'backend/.qa-backups'
    backup_dir.mkdir(exist_ok=True)
    if os.name != 'nt':
        subprocess.run(['sudo', 'chown', '10001:' + str(os.getgid()), str(backup_dir)], check=True)
        subprocess.run(['sudo', 'chmod', '770', str(backup_dir)], check=True)
    try:
        for arguments in [
            ['run', '-d', '--label', 'pesopilot.qa.run=' + state['run'], '--env-file', str(directory / 'sql.env'), '-e', 'ACCEPT_EULA=Y', '-e', 'MSSQL_PID=Developer', '-p', '127.0.0.1:1433:1433', '-v', str(backup_dir) + ':/var/opt/mssql/backup', 'mcr.microsoft.com/mssql/server:2022-latest'],
            ['run', '-d', '--label', 'pesopilot.qa.run=' + state['run'], '--env-file', str(directory / 'keycloak.env'), '-p', '127.0.0.1:8080:8080', '-v', str(directory / 'realm.json') + ':/opt/keycloak/data/import/realm.json:ro', 'quay.io/keycloak/keycloak:26.7.5', 'start-dev', '--hostname=http://localhost:8080', '--import-realm'],
        ]:
            state['containers'].append(docker(*arguments))
            state_path.write_text(json.dumps(state))
        connection = None
        for _ in range(90):
            try:
                connection = pyodbc.connect('DRIVER={ODBC Driver 18 for SQL Server};SERVER=127.0.0.1,1433;DATABASE=master;UID=sa;PWD=' + sql_password + ';Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=2', autocommit=True)
                break
            except pyodbc.Error:
                time.sleep(2)
        if connection is None:
            raise RuntimeError('Synthetic SQL Server did not become ready')
        connection.execute('CREATE DATABASE PesoPilot')
        connection.close()
        issuer = 'http://localhost:8080/realms/pesopilot'
        for _ in range(90):
            try:
                response = httpx.get(issuer + '/.well-known/openid-configuration', timeout=2)
                if response.status_code == 200 and response.json()['issuer'] == issuer:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2)
        else:
            raise RuntimeError('Synthetic identity provider did not become ready')
        url = 'mssql+pyodbc://sa:' + quote(sql_password, safe='') + '@127.0.0.1:1433/PesoPilot?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=yes'
        if os.environ.get('GITHUB_ACTIONS'):
            print('::add-mask::' + url)
        (root / 'backend/.env').write_text(f'DATABASE_URL={url}\nOIDC_ISSUER={issuer}\nOIDC_CLIENT_SECRET={client_secret}\nKEYCLOAK_ADMIN_PASSWORD={admin_password}\nAUTH_LIMIT=200\nAPI_LIMIT=10000\n')
        (root / 'backend/.env').chmod(0o600)
        if os.environ.get('GITHUB_ENV'):
            with Path(os.environ['GITHUB_ENV']).open('a') as file:
                file.write('QA_SERVER_BACKUP_DIR=/var/opt/mssql/backup\n')  # pragma: allowlist secret -- generated credential prefix or public environment variable
        print('Synthetic SQL Server and Keycloak ready. Credentials remain in ignored CI files.')
    except Exception:
        cleanup()
        raise


if __name__ == '__main__':
    {'start': start, 'cleanup': cleanup}[sys.argv[1]]()
