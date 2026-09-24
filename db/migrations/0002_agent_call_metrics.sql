-- Migration 0002 — agent_call_metrics (roadmap AI-8, ADR-0036).
-- Applied with: psql -v ON_ERROR_STOP=1 "$CGP_DB_URL" -f db/migrations/0002_agent_call_metrics.sql
-- Forward-only and idempotent: safe on a database built from 0001 (schema.sql),
-- and a no-op on one built from a schema.sql that already contains the table.
-- The table definition below must stay identical to the one in db/schema.sql.

-- ── agent_call_metrics: LLM observability for the variant agent (AI-8) ───────
-- One row per variant interpretation: LLM call count, tokens, latency and an
-- *estimated* cost (dated price table in ai-report/agent/observability.py,
-- stamped in price_table_version). Counts/ids only — no prompt/completion text,
-- no variant coordinates, no PHI. Token columns are NULL (never 0) when no call
-- reported usage; usage_complete says whether every call did. Insert-only.
-- Also shipped as a standalone forward migration: db/migrations/0002_agent_call_metrics.sql.
CREATE TABLE IF NOT EXISTS agent_call_metrics (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_pk                BIGINT REFERENCES runs(id),
    run_id                TEXT NOT NULL,
    backend               TEXT NOT NULL,
    model_id              TEXT NOT NULL,
    n_llm_calls           INTEGER NOT NULL CHECK (n_llm_calls >= 0),
    n_failed_calls        INTEGER NOT NULL DEFAULT 0 CHECK (n_failed_calls >= 0),
    n_calls_without_usage INTEGER NOT NULL DEFAULT 0 CHECK (n_calls_without_usage >= 0),
    prompt_tokens         INTEGER CHECK (prompt_tokens >= 0),
    completion_tokens     INTEGER CHECK (completion_tokens >= 0),
    usage_complete        BOOLEAN NOT NULL,
    llm_latency_ms        DOUBLE PRECISION NOT NULL CHECK (llm_latency_ms >= 0),
    wall_time_ms          DOUBLE PRECISION NOT NULL CHECK (wall_time_ms >= 0),
    estimated_cost_usd    NUMERIC(12, 8) CHECK (estimated_cost_usd >= 0),
    price_table_version   TEXT NOT NULL,
    fallback_triggered    BOOLEAN NOT NULL,
    recorded_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agent_call_metrics_backend ON agent_call_metrics(backend, recorded_at);
CREATE INDEX IF NOT EXISTS idx_agent_call_metrics_run ON agent_call_metrics(run_id);

-- Same guardrail as schema.sql: redefine forbid_mutation() (identical body,
-- so this is safe if it already exists) and attach the row + TRUNCATE triggers.
CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Table % is insert-only (append a correction instead)', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_immutable_agent_call_metrics ON agent_call_metrics;
CREATE TRIGGER trg_immutable_agent_call_metrics
  BEFORE UPDATE OR DELETE ON agent_call_metrics
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

DROP TRIGGER IF EXISTS trg_immutable_truncate_agent_call_metrics ON agent_call_metrics;
CREATE TRIGGER trg_immutable_truncate_agent_call_metrics
  BEFORE TRUNCATE ON agent_call_metrics
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();
