# Release checklist

- [x] Owner-isolation/session/security regression suite executed locally.
- [x] Finance versions, constraints, rollback and SQL Server concurrency verified.
- [x] Backend dependency audit, frontend dependency audit and Bandit executed.
- [x] Frontend production build/type check and HTTP security smoke executed.
- [x] Migration 0004 applied to local development SQL Server.
- [ ] Hosted CI verified and branch protection configured.
- [ ] Browser E2E, keyboard/a11y and responsive acceptance verified.
- [ ] Production provider MFA/recovery and trusted proxy settings reviewed.
- [ ] SQLAlchemy 17.x compatibility verified on approved dependency runtime.
- [ ] Privacy/retention/export/deletion and AI opt-in policies implemented.
- [ ] Runtime DB permissions, encryption at rest and backup access verified.
- [ ] Restore rehearsal and actual monitoring/alerting demonstrated.
- [ ] Deployment/rollback rehearsed on staging; production approval obtained.

Unchecked gates block real-user production. Checklist completion alone is not security assurance.
