# PesoPilot AI

PHP personal finance app with separate `frontend` (Next.js + TypeScript) and `backend` (FastAPI + SQLAlchemy + SQL Server) folders. `MD` contains the roadmap and implementation history.

## Implemented

- Monthly dashboard, accounts, transactions, category budgets and exact integer centavo calculations.
- CSV preview/confirmation, duplicate candidates and atomic exact-file repeat protection.
- Keycloak OpenID Connect login through Authlib, authorization code flow with PKCE, state and nonce validation.
- Opaque SQL Server sessions in `__Host-pesopilot` cookies: Secure, HttpOnly, SameSite=Lax, Path=/, no Domain. Only a token hash is stored in the database. No authentication tokens in localStorage.
- Eight-hour absolute / thirty-minute idle session expiry, rotation on login, server-side revocation on logout, and provider logout when available.
- CSRF token plus exact Origin checks on protected writes; user-scoped authorization on every finance endpoint; database ownership constraints.
- SQL Server rate limits shared across app workers and authentication event records without passwords, tokens or financial details.

This is an authenticated development application. Account edit/archive/restore, version-protected transaction editing, cursor pagination, and SQL aggregate dashboards are implemented. Transfers/refunds, AI, export/deletion, browser E2E, monitoring and production hardening remain roadmap work. See [current development status](MD/Development_Status.md).

Before starting an existing checkout after pulling these changes, stop the API, run `.venv/Scripts/python.exe -m alembic upgrade head` from `backend`, then restart it. Migration `0003` adds archive flags and edit versions without removing finance records. The configured workspace database was upgraded successfully.

## Start on this workspace

The Python virtual environment, ignored `backend/.env`, database migrations through `0002`, workspace-local Java/Keycloak runtimes, and local HTTPS certificate are already configured. Do not overwrite the existing `.env`. Restart any old backend process so it reads the updated configuration.

Run these in three terminals from the project root:

```powershell
# 1. Local Keycloak (no Docker required on this workspace)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File backend/keycloak/Start-Keycloak.ps1
```

```powershell
# 2. API — suppress access logs so callback authorization codes are not logged
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

```powershell
# 3. HTTPS frontend, port 3010
cd frontend
npm.cmd run dev
```

Open **https://localhost:3010**. The generated localhost certificate is self-signed; accept the browser's local certificate prompt for this development address. The generator does not install a CA or change system trust. `npm run dev` generates/renews the certificate using the backend environment before starting Next.js. `npm start` uses port 3010 behind an HTTPS reverse proxy for a production build.

Click **Sign in with Keycloak**, then **Register** to create a development user. A second user gets a separate workspace. Old demo records are preserved under isolated legacy identities and are never assigned to the first login. Create an account, then preview/confirm the synthetic CSV in the import tab; select October 2026 to see its totals.

The Keycloak admin console is http://localhost:8080/admin (username `admin`; its generated password is in the ignored `backend/.env` as `KEYCLOAK_ADMIN_PASSWORD`). Never commit that file or the local runtime data. API docs: http://127.0.0.1:8000/docs; protected writes require the application's cookie, `Origin` and `X-CSRF-Token`.

## Fresh checkout setup

Prerequisites: Node.js 20.9+, Python 3.11+, SQL Server Developer/Express for development, Microsoft ODBC Driver 18, plus Docker for the provider Compose option or OpenJDK 21 for the portable option.

1. Run `backend/setup.sql` through SSMS. Use a schema-capable migration identity for setup and a dedicated runtime identity with SELECT/INSERT/UPDATE/DELETE permissions for the app.
2. In `backend`, create `.venv`, install `requirements.txt`, copy `.env.example` to `.env`, configure `DATABASE_URL` and apply migrations:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env before continuing.
.\.venv\Scripts\python.exe -m alembic upgrade head
```

3. Start Keycloak using one of these options:

**Docker:** set `$env:KEYCLOAK_ADMIN_PASSWORD` to your own development admin password and run `docker compose -f backend/keycloak/compose.yml up -d` from the root. The `pesopilot` realm and confidential client are imported. In the admin console, open `pesopilot` realm → Clients → `pesopilot` → Credentials, regenerate/copy its client secret into `backend/.env` as `OIDC_CLIENT_SECRET`.

**Portable Windows:** download/extract OpenJDK 21 into `.tools/java/<jdk-directory>` and Keycloak 26.7.5 into `.tools/keycloak/keycloak-26.7.5`. Set independently generated `KEYCLOAK_ADMIN_PASSWORD` and `OIDC_CLIENT_SECRET` in the ignored `backend/.env`, then run `Start-Keycloak.ps1` above. The script imports the realm using your configured client secret. Existing realms are not overwritten; if you rotate the secret later, update it in the admin console and `.env` together.

The client allows only `https://localhost:3010/api/v1/auth/callback`, uses PKCE S256, and permits post-logout redirect only to `https://localhost:3010`. Password and implicit grants are disabled for the application. Local Keycloak uses its own development H2 store; PesoPilot finance, users and sessions use SQL Server. Keycloak's development setup is not a production configuration.

4. Run `npm.cmd ci` in `frontend`, then start all three services as above. Frontend `/api` requests proxy to `http://127.0.0.1:8000`; set server-side `API_URL` if your backend runs elsewhere. Database credentials remain on the server.

For local Windows SQL authentication use an appropriately URL-encoded login/password. For integrated authentication use `mssql+pyodbc://@localhost/PesoPilot?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&Encrypt=yes&TrustServerCertificate=yes`. Replace the server/instance as appropriate. Outside local development use a trusted database certificate with `TrustServerCertificate=no`, an HTTPS provider and an HTTPS frontend origin.

## Checks and evidence

```powershell
# In backend: unit/API tests with temporary SQLite databases
.\.venv\Scripts\python.exe -m pytest -q
# Real SQL Server, temporary users/data removed afterward
.\.venv\Scripts\python.exe smoke_sqlserver.py
# Real running Keycloak + SQL Server, temporary provider user removed afterward
.\.venv\Scripts\python.exe smoke_keycloak.py
# Optional: exercise the running HTTPS frontend proxy too
$env:SMOKE_THROUGH_FRONTEND='true'
.\.venv\Scripts\python.exe smoke_keycloak.py
```

```powershell
# In frontend
npm.cmd run typecheck
npm.cmd run build
```

Current checks: 49 backend tests; SQL Server migration `0003`; real SQL Server authorization/account/import/budget/reconciliation/edit/archive/pagination smoke; previously verified real Keycloak login/logout including the HTTPS frontend proxy (not rerun for this change); frontend production build and TypeScript check. Test provider accounts and finance smoke rows were removed. Browser interaction and accessibility audits are still pending.

The default fixed-window limits are 10 authentication/anonymous attempts and 120 authenticated requests per 60 seconds. Authentication uses the connection's IP address, ignoring untrusted forwarded headers; behind the frontend proxy it conservatively shares an authentication bucket. Review trusted-proxy client-IP handling before hosting a public service. `auth_events` records login, logout, expiry, rejected requests and rate-limit events. Production retention, alerting and provider back-channel logout are not implemented.

SQLAlchemy 2.0.40 still warns about the installed SQL Server 17.0 version; tested workflows passed. Windows Application Control blocked the newer binary previously attempted. Resolve this compatibility warning before deployment. Configure MFA/passkeys, registration policy, SMTP, provider backups and operational controls before processing real users' data.

References: [Authlib Starlette OIDC](https://docs.authlib.org/en/v1.6.9/client/starlette.html), [Keycloak local setup](https://www.keycloak.org/getting-started/getting-started-zip), [roadmap](MD/PesoPilot_AI_Production_Roadmap.md), [status and history](MD/Quick_Wins_Status.md).
