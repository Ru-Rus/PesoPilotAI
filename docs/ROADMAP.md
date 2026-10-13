# Current roadmap status

See [Engineering_Status](../MD/Engineering_Status.md) and the annotated [engineering prompt](../MD/AI_ENGINEERING_PROMPT.md) for measured progress. The following is the preserved full project roadmap.

﻿# PesoPilot AI — Production-Grade Full-Stack Roadmap

**Goal:** A recruiter-ready, security-first personal finance intelligence platform. **Timeline:** 16–20 part-time weeks, adjustable by velocity. **Initial scope:** manual accounts and CSV transaction imports; no bank credentials, payment execution, investment recommendations, or production bank integrations.

## 1. Product definition and success criteria

Users can sign in securely, create manual cash/e-wallet/bank accounts, import and manage transactions, review spending trends, set budgets, and ask an AI assistant questions about their own finances. AI outputs are advisory and cite deterministic calculations. Users control data sharing and can export/delete their data.

**MVP:** authentication; account management; transaction CRUD; CSV import preview and duplicate detection; budgets; dashboard; AI category suggestions; 3 evidence-based insight types; export; account deletion.

**Post-MVP:** custom rules, recurring transactions, multi-currency, explainable anomaly detection, advanced AI Q&A, shared households (requires redesigned authorization), mobile PWA, bank integrations only after separate compliance and threat review.

**Non-functional targets (initial SLOs, validate under load):** 99.5% monthly availability for a deployed public beta; p95 read API latency < 500 ms excluding AI/long-running jobs; p95 CSV import of 5,000 rows < 60 seconds on specified hardware; zero known critical/high exploitable vulnerabilities at release; 100% cross-user authorization test pass; restore rehearsal with documented RPO <= 24h and RTO <= 4h (only if infrastructure supports them). Never advertise achieved SLOs without measurements.

## 2. Stack and architecture

- Frontend: Next.js + TypeScript + Tailwind + shadcn/ui + Recharts; React Hook Form + Zod; Playwright, Vitest, axe accessibility checks.
- Backend: FastAPI + Pydantic + SQLAlchemy + Alembic; pytest + httpx + Hypothesis.
- Storage: SQL Server with separate least-privilege app/migration roles; Redis/Celery for jobs; private object storage for temporary imports only if necessary.
- Auth: reputable OIDC provider supporting MFA/passkeys; backend validates OIDC claims; opaque server-side sessions in Secure, HttpOnly, SameSite cookies, CSRF protection, session rotation and revocation. No tokens in localStorage.
- AI: provider abstraction, optional local Ollama for synthetic data; hosted provider for production only after privacy assessment, retention configuration, and consent. AI never receives full raw statements by default.
- Infrastructure: Docker, managed database preferred, TLS reverse proxy, secrets manager, CI/CD GitHub Actions, OpenTelemetry, error monitoring with PII scrubbing.

**Data flow:** Browser -> Next.js -> FastAPI (authn, authz, validation, rate limits) -> SQL Server. CSV upload -> quarantined temp storage -> validation -> preview -> user confirmation -> transactional import. Long tasks -> queue -> worker. AI -> deterministic aggregate/query service -> data minimization/redaction -> model -> schema validation -> evidence and confidence -> UI.

## 3. Data model and financial correctness

Tables: users, sessions (if self-managed), financial_accounts, transactions, categories, transaction_category_rules, import_batches, import_rows, budgets, ai_jobs, ai_insights, user_consents, security_audit_events, data_export_jobs, deletion_requests. Every user-owned row carries `user_id` (or joins through a checked owner). Include created_at, updated_at, version for concurrency where needed. Index `(user_id, occurred_at)` and other access paths.

**Financial invariants:** money stored as integer minor units (PHP centavos) or NUMERIC/Decimal, never floating-point; currency stored per account/transaction; all timestamps UTC and explicit transaction local dates; amounts and sign conventions documented; transfers between owned accounts excluded from income/expense aggregates; reversals/refunds treated consistently; recurring imports idempotent; stable transaction fingerprint is user-scoped and accounts for legitimate same-day same-amount transactions; dedupe is advisory unless a trustworthy external transaction ID exists. All totals calculated in backend SQL/Decimal, not by LLM.

## 4. Repository layout

```text
pesopilot-ai/
  frontend/                 # Next.js UI, frontend tests and public assets
  backend/                  # FastAPI, workers, models, migrations and backend tests
  MD/                       # Roadmap, architecture decisions and security documentation
  README.md                 # Local setup and verification
```

## 5. Phase plan and gates

### Phase 0 — Discovery and threat model (Week 1)

- Define personas, user stories, data classification, retention, consent and deletion requirements.
- Create architecture diagram, data-flow diagram, trust boundaries, STRIDE threat model and abuse-case register.
- Decide initial regulatory scope; evaluate Philippine Data Privacy Act and NPC guidance with qualified review before processing real user data; don't claim compliance solely from a checklist.
- Deliver: PRD, threat-model.md, ADRs, acceptance criteria, risk register, privacy notice draft.
- **Gate:** documented owners for every sensitive data flow, high-risk threats have mitigation plans.

### Phase 1 — Developer platform (Week 2)

- Monorepo, formatting, lint, type checking, pre-commit hooks, dependency pinning, reproducible Docker Compose, sample environment file (no secrets), staging environment.
- GitHub Actions for unit tests, lint, type checks, SAST, secret scanning, dependency scanning; branch protection and review rules.
- **Gate:** clean checkout boots app and runs tests; no secrets in history; CI blocks failed checks.

### Phase 2 — Identity, sessions and authorization (Weeks 3–4)

- OIDC login and MFA, email verification if supported, secure cookie sessions, CSRF, logout/revoke, rate limits, security event logs, self-service session management.
- Build reusable service-layer owner checks and deny-by-default permissions. Add two-user cross-tenant tests to every resource route.
- **Gate:** anonymous requests denied; user A cannot read/update/delete user B records; sessions revoked after logout; auth bypass and CSRF tests pass.

### Phase 3 — Accounts and transaction engine (Weeks 5–6)

- Create/edit/archive accounts; transaction CRUD, filtering, pagination, categories, validation and Decimal-based financial calculations.
- Define handling for transfers, refunds, edits, duplicates, concurrent updates, zero and negative values.
- **Gate:** property-based accounting invariants, API contract tests, ownership tests, reconciliation fixtures all pass.

### Phase 4 — Safe CSV ingestion (Week 7)

- Strict size/row limits, MIME/extension/content validation, streaming parser, encoding checks, CSV dialect handling, column mapping and preview, date/amount locale validation, idempotency, import state machine and rollback.
- Treat CSV text as untrusted. Never execute spreadsheet formulas; escape dangerous leading characters on exports intended for spreadsheets. Never parse arbitrary PDFs in MVP.
- **Gate:** malformed/oversized/hostile CSV cases rejected safely; duplicate imports do not silently double-count; partial failure recoverable.

### Phase 5 — Dashboard, budgets and UX (Weeks 8–9)

- Deterministic monthly income/expense/net flow, category charts, account summaries, budget alerts, responsive design, empty/loading/error states, keyboard navigation.
- **Gate:** dashboard reconciles with source transactions; budget boundary tests pass; WCAG 2.2 AA-oriented checks and core browser E2E tests pass.

### Phase 6 — AI intelligence (Weeks 10–12)

- Start with deterministic category rules, then model-assisted classification with user confirmation and confidence thresholds.
- Compute trends and anomalies deterministically (e.g. month-over-month variance, recurring merchant spikes) before LLM explanation. AI answers restricted to authorized, aggregated tool results; allowlisted read-only tools; no arbitrary SQL generation/execution.
- Explicit opt-in for external model processing, data minimization, provider configuration, per-user quotas, timeout/retry/backoff/circuit breaker, output schema validation, traceable calculation IDs, user feedback.
- **Gate:** prompt injection cannot trigger data access outside scope or unauthorized writes; sensitive fields absent from prompts/logs by default; unsupported claims flagged; provider failure degrades gracefully.

### Phase 7 — Hardening and QA (Weeks 13–14)

- Full regression, load tests, authz penetration-style tests, API fuzzing, dependency/container scans, accessibility audit, backup restore exercise, threat-model review.
- **Gate:** no open critical/high exploitable findings; release checklist signed off; tests and recovery evidence captured.

### Phase 8 — Production beta (Weeks 15–16)

- Staging/prod separation, managed SQL Server, TLS, WAF/rate limits where suitable, restricted network exposure, backups, migration rollback plan, alerting, incident response runbook, canary deployment and smoke tests.
- Release to synthetic/demo users first; invite real users only after privacy and operational controls are verified.
- **Gate:** tested deployment and rollback; measured baseline SLOs; monitoring/alerts work; backup restore validated.

### Phase 9 — Recruiter-ready portfolio (Weeks 17–20)

- Seeded public demo with synthetic data; screenshots/GIF; architecture and data flow diagrams; API docs; ADRs; test matrix; CI badges; load-test report; security posture and limitations; postmortem of one simulated incident.
- Publish honest performance numbers and known limitations, never claim certification or absolute security.
- **Gate:** a reviewer can run the app locally, see a safe demo, and understand tradeoffs in under 10 minutes.

## 6. API design (v1 examples)

`GET /health/live`, `GET /health/ready` (minimal public data); `GET /api/v1/me`; `GET|POST /api/v1/accounts`; `PATCH|DELETE /api/v1/accounts/{id}`; `GET|POST /api/v1/transactions`; `GET|PATCH|DELETE /api/v1/transactions/{id}`; `POST /api/v1/imports` (initiate); `GET /api/v1/imports/{id}/preview`; `POST /api/v1/imports/{id}/confirm`; `GET /api/v1/budgets`; `POST /api/v1/budgets`; `GET /api/v1/analytics/summary`; `POST /api/v1/ai/categorize`; `POST /api/v1/ai/insights`; `POST /api/v1/ai/questions`; `POST /api/v1/me/export`; `DELETE /api/v1/me` (verified, asynchronous deletion workflow). All sensitive endpoints require authentication and user-scoped authorization. Cursor pagination, request IDs, structured errors, bounded filtering, API versioning and idempotency keys for relevant writes.

## 7. Security requirements checklist

- [ ] ASVS 5.0 Level 2 as a **target verification baseline**, mapped by control IDs; document exceptions. External audit needed before any assurance claim.
- [ ] Threat model: cross-tenant access, credential stuffing, CSRF, XSS, SQL injection, CSV formula injection, import resource exhaustion, queue poisoning, LLM prompt injection, provider data leakage, backup exposure.
- [ ] Least privilege at API, worker, database and cloud layers; deny by default; no direct database access from browser.
- [ ] Strong MFA/passkey support; secure session lifecycle; rate limiting; account recovery protections; reauthentication for export/delete.
- [ ] Parameterized queries, strict Pydantic validation, output encoding, CSP, restrictive CORS, security headers, HTTPS/HSTS, CSRF protection.
- [ ] Data encryption in transit and at rest; managed keys and rotation policy; restricted backup access; secrets manager, never committed credentials.
- [ ] Privacy by design: synthetic fixtures, minimal collection, documented retention and deletion, explicit AI-sharing consent, sensitive data redaction in logs/telemetry.
- [ ] No financial values or credentials in URL paths/query strings, analytics trackers, exception traces or LLM logs.
- [ ] Safe file ingestion: size and row caps, quarantine, parse limits, temporary retention, no shell execution, safe CSV export.
- [ ] AI read-only by default, bounded tool scopes, prompt-injection defenses, schema validation, no raw SQL from model, human confirmation for changes.
- [ ] Security audit logs for auth, authorization failures, imports, exports, deletion and admin actions; integrity and retention controls.
- [ ] Automated SAST/SCA/container/secret scanning and manual security review before releases.
- [ ] Incident response, restore drills, documented recovery objectives, alerting and vulnerability disclosure instructions.

## 8. QA strategy and test matrix

| Layer          | Cases                                                                             | Tool                                            | Gate                                                                                         |
| -------------- | --------------------------------------------------------------------------------- | ----------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Unit           | amount parsing, rounding, sign, transfer, budget boundaries, category rules       | pytest/Vitest                                   | >=85% line coverage of critical backend logic; 100% defined financial invariants             |
| Property-based | amounts, timezones, import idempotency, invariants under random inputs            | Hypothesis                                      | No counterexamples in agreed suite                                                           |
| Integration    | SQL Server migrations, transactions, queue retries, import rollback               | pytest + Testcontainers                         | All pass                                                                                     |
| API contract   | validation, pagination, errors, generated OpenAPI client                          | httpx, schema checks                            | No breaking mismatch                                                                         |
| Authz          | anonymous, expired session, IDOR/BOLA, user A vs B, mass assignment               | pytest                                          | 100% of user-owned resource routes covered and passing                                       |
| E2E            | signup/login, CSV preview/confirm, dashboard, budget, AI opt-in, export/delete    | Playwright                                      | All critical journeys pass on supported browsers                                             |
| Security       | CSRF, XSS, injection, upload abuse, rate limiting, secrets, dependency risks      | OWASP ZAP, Semgrep, Gitleaks, Trivy             | No untriaged critical/high exploitable issues                                                |
| AI eval        | classification quality, groundedness, prompt injection, privacy leakage, fallback | fixed synthetic golden dataset + red-team cases | Pre-agreed accuracy/groundedness thresholds, zero unauthorized data disclosure in test suite |
| Accessibility  | keyboard, labels, focus, contrast, screen reader spot-check                       | axe + manual                                    | No critical accessibility blockers                                                           |
| Performance    | concurrent reads, 5k-row imports, AI quota/timeouts                               | k6/Locust                                       | Measured SLO targets on stated hardware                                                      |
| Resilience     | DB/Redis/model outages, retry, duplicate jobs, restore                            | fault injection + runbooks                      | No double posting, graceful errors, successful restore                                       |

**Suggested AI evaluation targets:** >=90% category top-1 accuracy on representative _synthetic or consented labeled_ test transactions; >=95% grounded answers on a fixed question set; 0 unauthorized cross-user disclosures in adversarial tests. Targets are goals, not guarantees; measure and report actual results. Require manual confirmation for low-confidence predictions.

## 9. Example high-priority QA scenarios

1. User A requests `/transactions/{user_B_id}`: return 404 or 403 without data disclosure; test read, edit, delete, export, background jobs.
2. A statement imported twice: duplicate candidates identified, no accidental double-count after confirmation.
3. Two legitimate purchases with same merchant/amount/date: both preserved when external IDs differ or user confirms.
4. Import with `=HYPERLINK(...)` and malicious prompt-like memo: no execution; safely escaped on spreadsheet export; no instruction following by AI.
5. Decimal cases: 0.01 + 0.02 = 0.03 exactly; refunds and transfers reconcile.
6. Expired/revoked session and forged CSRF: denied.
7. Model says 'delete all transactions' embedded in CSV: tool scope forbids it; no deletion.
8. Model provider offline: deterministic dashboards still work; AI job returns bounded retry/failure.
9. User requests data deletion: session revocation, job cancellation, deletion from active stores, documented backup retention/expiry and audit evidence.
10. Import interrupted halfway: no half-committed transaction batch, safe retry.
11. Concurrent budget edits: version conflict handled predictably.
12. AI prompt asks for another user's spending: backend owner-scoped tools deny, even if model attempts tool call.

## 10. CI/CD quality gates

Pull request: formatting -> static typing -> unit/property tests -> integration/contract -> authz tests -> frontend build -> E2E smoke -> SAST/SCA/secret scan -> container scan -> review. Protect main branch, require checks, disallow force push. Deployment: tagged immutable image, migration compatibility check, staging deploy, smoke tests, manual production approval, rolling/canary deploy, post-deploy monitoring and rollback instructions. Pin GitHub Actions to immutable revisions and minimize workflow permissions.

## 11. Operational readiness

- Environments: local, CI, staging, production; separate credentials and databases.
- Alerts: 5xx rate, p95 latency, job failures, auth anomalies, database saturation, backup failures, AI spend and quota.
- Backups: encrypted automated backups, restore test, retention policy and access control; backups not equivalent to tested disaster recovery.
- Privacy: no third-party analytics on sensitive pages by default; consent and data-processing inventory; documented provider policies.
- Costs: start with synthetic demo and local services; model requests capped and cached only when privacy-safe; verify current hosting/API pricing separately.
- Home Ubuntu laptop: suitable for demo/staging after firewall, updates, TLS, restricted ingress and backups; do not host real users' financial data there until independent security, reliability, physical-access and compliance review.

## 12. Recruiter-facing deliverables

README with problem statement, screenshots, demo credentials for **synthetic** data, architecture, quickstart, API docs, test instructions, security posture and limitations. Include 3 ADRs (e.g. Decimal money, session auth, AI guardrails), threat model (sanitized), test coverage and CI badges, performance report, deployment diagram, CHANGELOG, SECURITY.md, and a short demo video. Git history should show meaningful feature branches and reviewed pull requests, not one giant commit.

## 13. Definition of Done (every feature)

- [ ] Acceptance criteria and abuse cases documented.
- [ ] Schema/API contracts and migrations reviewed.
- [ ] Backend authorization and validation implemented.
- [ ] Unit/integration/negative/security tests written and passing.
- [ ] Frontend handles loading, empty, errors, keyboard and mobile.
- [ ] No sensitive logging or unexpected AI data sharing.
- [ ] Observability, docs and rollback implications reviewed.
- [ ] CI green; peer/self-review completed; demo verified in staging.

## 14. First ten implementation tickets

1. `docs: write PRD, personas, threat model, scope and acceptance criteria`
2. `chore: bootstrap Next.js/FastAPI monorepo and Docker Compose`
3. `ci: add lint, typing, test, dependency and secret scans`
4. `feat(auth): integrate OIDC with secure server-side sessions and MFA`
5. `test(security): add cross-user access-control test harness`
6. `feat(accounts): account model, CRUD and owner-scoped APIs`
7. `feat(transactions): Decimal-safe transaction service and API`
8. `test(finance): add property-based financial invariant tests`
9. `feat(import): CSV preview, mapping, validation and idempotent commit`
10. `feat(dashboard): reconciled monthly summary and category visualizations`

## 15. Authoritative security references

- OWASP ASVS 5.0: https://github.com/OWASP/ASVS/tree/master/5.0/en
- OWASP API Security Top 10: https://owasp.org/API-Security/
- OWASP File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- OWASP CSV Injection: https://owasp.org/www-community/attacks/CSV_Injection
- OWASP LLM Prompt Injection Prevention: https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html
- NIST AI RMF: https://www.nist.gov/itl/ai-risk-management-framework

**Final caution:** This plan targets production engineering practices, not a certification or guarantee of safety. A real public financial-data service needs independent review, legal/privacy assessment, and validated operational controls before onboarding users.
