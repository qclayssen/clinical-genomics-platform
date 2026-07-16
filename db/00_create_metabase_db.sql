-- Create a separate database for Metabase internal state.
-- This avoids table name collisions with the CGP schema (e.g., audit_log).
-- Runs before schema.sql because Postgres sorts initdb scripts alphabetically.

SELECT 'CREATE DATABASE metabase OWNER cgp'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'metabase')\gexec
