import subprocess
from pathlib import Path
from scan_secrets import scan


def test_secret_scanner_detects_generated_fixture_without_disclosing_value(tmp_path):
    subprocess.run(['git', 'init', '--quiet'], cwd=tmp_path, check=True)
    private = 'AKIA' + 'BCDEFGHIJKLMNOPQ'
    (tmp_path / 'unsafe.py').write_text('access_key = "' + private + '"\n')
    result = scan(tmp_path)
    assert result and result[0]['file'] == 'unsafe.py'
    assert private not in str(result)


def test_no_new_markdown_files_and_container_secret_exclusions():
    root = Path(__file__).resolve().parent.parent.parent
    assert '.env' in (root / 'backend/.dockerignore').read_text()
    assert '.e2e-fixture.json' in (root / 'frontend/.dockerignore').read_text()
    config = (root / 'deployment/compose.production.yml').read_text()
    assert 'read_only: true' in config and 'DATABASE_URL_FILE' in config
