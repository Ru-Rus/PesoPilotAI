# Security posture

OWASP ASVS Level 2 is a target, not an achieved assurance level. Implemented controls: Authlib OIDC/PKCE/claim verification; hashed opaque sessions; Secure HttpOnly SameSite cookies; exact-origin CSRF; owner-scoped queries and database ownership FKs; rate limits; server-generated request IDs; sanitized errors/log fields; bounded bodies/CSV; SQL financial constraints; read-only CI permissions; dependency audit and Bandit gates.

Frontend nonce CSP restricts scripts, framing, objects and connections; inline styles remain allowed for existing charts. Dynamic rendering supplies fresh script nonces. HSTS must be set by the eventual HTTPS ingress after domain/TLS verification; it is not set on local HTTP. CORS is disabled; browser access is same-origin through Next.js.

Set APP_ENV=production to require HTTPS OIDC, configured provider credentials, and explicit SQL Server Encrypt=yes / TrustServerCertificate=no. These startup guards do not provision TLS, database encryption at rest, backup access, MFA or recovery. The provider's local realm is development configuration. Never expose it as production unchanged.

Logs record request ID/status/timing and event names, without URLs, bodies, query strings, tokens or exception text. Run Uvicorn with --no-access-log to keep OIDC callback codes out of access logs. Reverse-proxy and infrastructure log scrubbing remains an operator requirement.

Remaining release blockers: MFA/recovery policy, audit retention/alerts, privacy/consent/export/deletion, encrypted backup/restore rehearsal, production least privilege, hosted CI/secret/container scans and browser verification. No hosted AI receives data. See [threat model](THREAT_MODEL.md) and [release checklist](RELEASE_CHECKLIST.md).
