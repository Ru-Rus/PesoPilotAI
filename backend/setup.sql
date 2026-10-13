-- Run as a database administrator once, on your development SQL Server.
IF DB_ID(N'PesoPilot') IS NULL
    CREATE DATABASE PesoPilot;
GO
-- Create a dedicated login/user using your own password via SSMS.
-- Use a migration principal with schema permissions for `alembic upgrade head`.
-- The runtime app principal needs SELECT, INSERT, UPDATE, DELETE only.
-- Do not use sa as the application's database login.
