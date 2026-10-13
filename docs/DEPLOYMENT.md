# Deployment procedure and runbook

Status: documented preparation only. No staging/production deployment is provisioned or approved.

1. Select separate staging/prod identities, database and OIDC realm. Keep local synthetic data separate. Configure provider MFA/recovery/registration and backups.
2. Install pinned dependencies; build frontend and run all quality gates. Inject secrets from deployment configuration; never include `.env` or certificates in artifacts.
3. Set APP_ENV=production with HTTPS provider/frontend and verified SQL Server TLS. Provide API_URL privately to Next.js. Terminate browser HTTPS at a restricted ingress, set HSTS only on the verified production domain, restrict direct API/DB access and disable callback query logging.
4. Back up the database and verify the backup before schema changes. Stop writers or use a reviewed deployment migration window. Use a schema-capable migration identity for `alembic upgrade head`; runtime identity must not have DDL permissions.
5. Start API with --no-access-log; start Next.js behind HTTPS. Check /health/live and /health/ready. Run synthetic smoke only in local/staging, then validate login/logout and UI journeys. Never run destructive smoke against real-user production without a separate review.
6. Monitor status/timing via request-ID logs. Central error monitoring, metrics and tracing remain unconfigured; configure them without financial payloads.

Rollback: preserve backups and prior immutable build/dependency set. Additive columns permit a reviewed code rollback while keeping the schema. Older clients that omit version preconditions cannot be mixed with the new API. Do not automatically downgrade the schema; dropping version columns/constraints requires separate review. Do not overwrite the current `.env`.

Database outage: readiness returns 503; protected DB failures return generic errors with request IDs. Preserve audit/backup evidence and restore service before retrying writes. Provider outage: login fails closed; local logout still revokes; deterministic finance does not depend on provider calls for an already-valid session.

Backup plan (not executed): encrypted SQL Server full backups with restricted access and defined retention; restore into an isolated empty database, apply integrity checks and reconcile known synthetic totals. Record measured RPO/RTO and recovery commands only after an actual rehearsal. No worker queue exists; worker operations are currently not applicable. Container Compose files currently cover local SQL Server and provider only; app container images and resource/ingress limits remain partial.
