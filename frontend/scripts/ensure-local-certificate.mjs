import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const candidate = fileURLToPath(new URL(process.platform === 'win32' ? '../../backend/.venv/Scripts/python.exe' : '../../backend/.venv/bin/python', import.meta.url));
const python = existsSync(candidate) ? candidate : (process.platform === 'win32' ? 'python' : 'python3');
const result = spawnSync(python, [fileURLToPath(new URL('../../backend/create_dev_certificate.py', import.meta.url))], { stdio: 'inherit' });
if (result.error) console.error('Set up the backend Python environment before starting local HTTPS.', result.error.message);
process.exit(result.status ?? 1);
