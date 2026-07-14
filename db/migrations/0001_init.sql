-- Migration 0001 — initial schema.
-- Applied with: psql "$CGP_DB_URL" -f db/migrations/0001_init.sql
-- Or via any migration runner (flyway/sqlx/alembic-sql). Migrations are forward-only,
-- consistent with the insert-only, change-controlled design of the platform.
\i db/schema.sql
