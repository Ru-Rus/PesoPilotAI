-- Apply with a migration/operator principal; does not alter existing identities.
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'pesopilot_runtime')
    CREATE ROLE pesopilot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.users TO pesopilot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.auth_sessions TO pesopilot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.login_flows TO pesopilot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.rate_buckets TO pesopilot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.auth_events TO pesopilot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.financial_accounts TO pesopilot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.transactions TO pesopilot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.budgets TO pesopilot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.import_batches TO pesopilot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.model_consents TO pesopilot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.transfers TO pesopilot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.refunds TO pesopilot_runtime;
GRANT SELECT, INSERT ON dbo.deletion_receipts TO pesopilot_runtime;
DENY CREATE TABLE, CREATE VIEW, CREATE PROCEDURE, CREATE FUNCTION TO pesopilot_runtime;
REVOKE CONTROL ON SCHEMA::dbo FROM pesopilot_runtime;
DENY ALTER ON SCHEMA::dbo TO pesopilot_runtime;
DENY INSERT, UPDATE, DELETE ON dbo.alembic_version TO pesopilot_runtime;
