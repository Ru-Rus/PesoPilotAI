# PesoPilot AI

Local development foundation for a PHP personal finance app. The application has two separate folders: `frontend` (Next.js + TypeScript) and `backend` (FastAPI + SQLAlchemy + SQL Server). `MD` retains the planning documents.

## Implemented quick wins

- Responsive dashboard with monthly income, expenses, net flow and account balances.
- Create cash, bank and e-wallet accounts; add/list/delete transactions.
- Monthly category budgets with remaining/overspent amounts.
- CSV preview and transactional confirmation, duplicate candidates, exact-file repeat protection.
- Integer centavo accounting, owner-scoped queries, fail-closed demo access.
- SQL Server schema migrations, synthetic CSV example, backend tests.

This is a single synthetic local workspace, not a multi-user release. Authentication, secure sessions/CSRF, account editing/archiving, transaction editing, transfers/refunds, pagination, AI, export/deletion, observability and release hardening remain roadmap work. No external AI processing is enabled.

## Local setup (PowerShell)

Prerequisites: Node.js 20.9+, Python 3.11+, SQL Server (Developer/Express for local use), and Microsoft ODBC Driver 18. SQL Server can be installed locally or started with `backend/compose.yml` if Docker Desktop is available. Developer edition is for development/testing.

1. In SSMS, run `backend/setup.sql` against your development instance. Create a dedicated SQL login and database user. Use a schema-capable migration principal for setup, then switch to a runtime principal with only SELECT/INSERT/UPDATE/DELETE permissions. Never use the admin login for the app.
2. Set up the backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env with your server, database, login, password and driver.
# URL-encode special characters in username/password.
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The sample uses encrypted transport with `TrustServerCertificate=yes` for a local self-signed certificate. Use `TrustServerCertificate=no` and a trusted server certificate outside local development. For Windows integrated authentication, use `mssql+pyodbc://@localhost/PesoPilot?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&Encrypt=yes&TrustServerCertificate=yes`. Configure the appropriate instance/server name for your installation.

3. In a second terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open http://127.0.0.1:3000. API docs: http://127.0.0.1:8000/docs. Create an account, then preview and confirm the synthetic CSV from the import tab. The sample dates are October 2026; select that reporting month to see its totals. The frontend proxies `/api` to the backend, so database credentials never enter the browser. Override `API_URL` in the frontend environment if needed.

## Checks

```powershell
# backend directory
.\.venv\Scripts\python.exe -m pytest -q
# frontend directory
npm.cmd run typecheck
npm.cmd run build
```

Unit/API tests use a temporary SQLite database to test application behavior; they do not establish SQL Server compatibility. Before using real records, run migrations and the full account/import/budget workflow against SQL Server. Disable `DEMO_MODE` to deny finance routes until a real authentication dependency replaces the synthetic owner. Keep both development servers bound to loopback.

## Verification on this workspace

The local `PesoPilot` database was created and migration `0001` applied using Windows integrated authentication. An ignored `backend/.env` is configured for that instance, and `backend/.venv` is ready. The runtime currently uses your Windows identity; configure a dedicated least-privilege identity before deployment.

Frontend production build and TypeScript checks passed. All 13 backend tests passed. The real SQL Server smoke check passed readiness, account/transaction creation, CSV preview/import/repeat rejection, budgets and exact balance reconciliation; temporary smoke rows were removed. Browser interaction/accessibility checks have not been run.

SQLAlchemy 2.0.40 emits an unrecognized-server-version warning for the installed SQL Server 17.0 instance, although the tested workflows passed. An attempted newer SQLAlchemy binary was blocked by Windows Application Control, so the tested version was retained. Resolve that compatibility warning before expanding SQL Server features or deploying.

Run the database smoke check again from `backend` with `.\.venv\Scripts\python.exe smoke_sqlserver.py`; it creates and removes only its own synthetic records.

See [the roadmap](MD/PesoPilot_AI_Production_Roadmap.md) and [implementation status](MD/Quick_Wins_Status.md).
