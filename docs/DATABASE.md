# Database and migrations

SQL Server remains the primary database. Migration order: 0001 finance, 0002 OIDC identities/sessions and ownership FKs, 0003 account archive/edit versions, 0004 budget versions, amount/kind/version checks and owner-account-page index.

`0004` preserves records and validates constraints. Invalid existing rows abort migration instead of being rewritten. Apply with a migration principal; run the app with SELECT/INSERT/UPDATE/DELETE only. `backend/setup.sql` describes role separation; enforcing existing runtime permissions is an operator task.

Finance writes use account `UPDLOCK, HOLDLOCK, ROWLOCK` hints on SQL Server. Archive edits acquire the same lock; multi-account edits lock account IDs in sorted order. Locks last until commit/rollback. SQL Server smoke proves an attempted posting waits for an archive commit and then rejects the archived account. SQLite unit tests do not prove SQL Server locking behavior. Failed imports roll back batch, rows and success audit together.

Version updates are conditional SQL statements; budget and transaction edits cannot silently replace a newer version. DELETE is conditional on the client version. Constraints enforce positive bounded amounts, supported kinds and positive versions. Audit rows contain event type, owner and UTC timestamp, not amounts/descriptions.

SQL Server reports 17.0.1000.7. Installed SQLAlchemy 2.0.40 has a version-recognition range excluding 17, confirmed in local dialect source. Upstream [discussion 13180](https://github.com/sqlalchemy/sqlalchemy/discussions/13180) explains this range and its historical origin. Real workflows pass, but full compatibility is not established. Keep the warning visible; a separately verified dependency upgrade remains pending. Do not edit installed dialect code to silence it. Lock semantics follow [Microsoft table-hint documentation](https://learn.microsoft.com/en-us/sql/t-sql/queries/hints-transact-sql-table).
