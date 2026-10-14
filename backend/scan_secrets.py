"""Offline secret scan of tracked and nonignored source; output is redacted."""
import json
import subprocess
from pathlib import Path
from detect_secrets.core.secrets_collection import SecretsCollection
from detect_secrets.settings import default_settings


def scan(root):
    result = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root, check=True, capture_output=True)
    collection = SecretsCollection(root=str(root))
    with default_settings():
        for filename in set(result.stdout.decode().split('\0')):
            if not filename or filename.endswith(('.lock', '.baseline')) or not (root / filename).is_file():
                continue
            collection.scan_file(filename)
    return [{'file': name, 'line': item.line_number, 'type': item.type} for name in collection.files for item in collection[name]]


if __name__ == '__main__':
    findings = scan(Path(__file__).resolve().parent.parent)
    print(json.dumps({'findings': findings, 'scope': 'tracked and nonignored source, no secret values or network verification'}))
    raise SystemExit(1 if findings else 0)
