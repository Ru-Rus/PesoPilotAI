# Test strategy

Install `backend/requirements-dev.txt` in the project environment. From backend:

```powershell
.venv/Scripts/python.exe -m pytest -q --cov=app --cov-fail-under=85 --cov-report=term-missing --cov-report=xml:coverage.xml
.venv/Scripts/python.exe -m pyflakes app tests smoke_concurrency.py
.venv/Scripts/python.exe -m bandit -r app -q
.venv/Scripts/python.exe -m pip_audit -r requirements.txt
.venv/Scripts/python.exe smoke_sqlserver.py
.venv/Scripts/python.exe smoke_concurrency.py
```

SQLite API tests verify identity/isolation/validation, exact finance, rollback, version conflicts, revocation races and bounded uploads. Authlib fixtures exchange actual signed provider tokens. Hypothesis generates integer-centavo pairs and checks exact addition. SQL Server scripts separately exercise database dialect, ownership, imports and bounded real concurrency with self-cleaning synthetic users.

Frontend: `npm.cmd run typecheck`, `npm.cmd run build`, `npm.cmd audit --audit-level=high`. Serve a production build on loopback 3011, then `node scripts/smoke-security.mjs` to verify actual response headers and distinct CSP script nonces. This is an HTTP smoke, not browser E2E or accessibility verification.

CI reports overall coverage with an 85% gate. No performance SLO, full AI eval, browser/a11y pass or restore result is claimed. Current evidence and exact counts are in [Engineering_Status](../MD/Engineering_Status.md).
