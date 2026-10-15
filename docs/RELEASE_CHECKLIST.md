# Release checklist

Verified locally on 2026-10-15. Unchecked gates still block real-user production.

- [x] Mypy: all 11 application modules pass; typing tools pinned and check added to CI.
- [x] Backend: 107 tests pass, 94.58% coverage; authentication identity-race safeguards covered.
- [x] Frontend: lint, typecheck, 14 tests and production build pass; statement coverage 68.56%, line coverage 70.05%.
- [x] All seven Playwright workflows pass together, including TOTP enrollment/login, financial reconciliation, authorization, CSRF, expiry, deletion, accessibility and responsive layouts.
- [x] Combined local E2E uses process-only AUTH_LIMIT=200 / API_LIMIT=10000, matching existing CI fixture configuration. Default development limits can throttle the complete suite; production defaults are unchanged.
- [x] Backend runtime/development dependency audits and frontend audit report no known vulnerabilities. Bandit, Pyflakes and redacted secret scan pass.
- [x] Production HTTP smoke verifies security headers, no-store and distinct rendered CSP nonces.
- [x] Synthetic SQL Server concurrency checks pass for edits, budgets, imports, archive/write serialization, bounded refunds and idempotent transfers.
- [x] Disposable databases verify migrations 0001-0006, rollback/re-upgrade 0006-0004-0006, checksum backup/restore, integrity checks and exact three-centavo reconciliation. Restore measured 685.268 ms locally; production recovery objectives remain unverified.
- [x] Isolated SQL principal verifies runtime DML grants and denial of migration updates/DDL; production login assignment remains unverified.
- [x] Regression tests verify protected telemetry, privacy-safe traces, alert evaluation, retention dry-run/owner scope, AI consent, injection rejection and model-output validation.
- [x] Local Keycloak configuration inspected: six-digit, 30-second TOTP, brute-force protection enabled and password reset disabled. TOTP enrollment is optional (defaultAction=false).
- [x] Workflow and Compose YAML parse. Latest accessible hosted run 38581972442 has a successful integration job.
- [ ] Hosted checks/container jobs pass for the final changes. Latest accessible run failed backend analysis and Trivy; detailed job logs return HTTP 403 without authentication. Changes have not been pushed or run remotely.
- [ ] Docker image build/run/scan and Caddy runtime/TLS validation: Docker and Caddy executables unavailable locally.
- [ ] Real Ollama inference: no Ollama executable or listening service at 127.0.0.1:11434; no model downloaded.
- [ ] Production MFA enforcement, recovery procedure and trusted-proxy policy: no provisioned production provider. Local TOTP success does not establish mandatory MFA or recovery readiness.
- [ ] Production verified SQL Server TLS, actual runtime login least privilege, encryption at rest and encrypted backups: production infrastructure/certificates/identities unavailable. Disposable recovery backup was not encrypted.
- [ ] External telemetry scraping/notifications and retention scheduler: no provisioned production operator/scheduler. Existing process-local alerts and explicit maintenance.py cleanup are tested; no cleanup was scheduled against existing user data.
- [ ] Production SQL Server/driver compatibility, staging deployment/rollback, branch protection and production approval verified on the intended hosted target.

Hosted run inspected: https://github.com/Ru-Rus/PesoPilotAI/actions/runs/38581972442
No expensive scale benchmark repeated: changes preserve database query structure and money representation; existing concurrency and financial workflows were rerun.
