-- Clinical Genomics Insight Platform — Postgres schema
--
-- Design principle: traceability by construction. runs / qc_metrics / run_provenance
-- / audit_log are INSERT-ONLY. There is no UPDATE or DELETE path in the application —
-- a correction is a new run row, never an overwrite. This mirrors ISO 15189 record
-- amendment (append a correction; never erase the original).

-- ── samples ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS samples (
    sample_id       TEXT PRIMARY KEY,
    reference_build TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── runs: one row per pipeline execution ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS runs (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id           TEXT NOT NULL UNIQUE,          -- Nextflow run name
    sample_id        TEXT NOT NULL REFERENCES samples(sample_id),
    pipeline_version TEXT NOT NULL,
    git_commit       TEXT NOT NULL,
    caller           TEXT NOT NULL,
    started_at       TIMESTAMPTZ,
    exported_at      TIMESTAMPTZ,
    validation_pass  BOOLEAN NOT NULL,
    ingested_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_runs_sample ON runs(sample_id);
CREATE INDEX IF NOT EXISTS idx_runs_version ON runs(pipeline_version);

-- ── qc_metrics: per-run QC + validation numbers ───────────────────────────────
CREATE TABLE IF NOT EXISTS qc_metrics (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_pk              BIGINT NOT NULL REFERENCES runs(id),
    percent_duplication DOUBLE PRECISION,
    snp_precision       DOUBLE PRECISION,
    snp_recall          DOUBLE PRECISION,
    snp_f1              DOUBLE PRECISION,
    n_variants          INTEGER,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_qc_run ON qc_metrics(run_pk);

-- ── run_provenance: checksums + versions for full traceability ─────────────────
CREATE TABLE IF NOT EXISTS run_provenance (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_pk          BIGINT NOT NULL REFERENCES runs(id),
    input_checksums JSONB NOT NULL,                 -- {filename: sha256}
    truth_version   TEXT,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── audit_log: append-only trail of every action against a run ─────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_pk      BIGINT REFERENCES runs(id),
    action      TEXT NOT NULL,                      -- e.g. INGEST, REPORT_DRAFTED
    detail      TEXT,
    actor       TEXT NOT NULL DEFAULT current_user,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_log(run_pk);

-- ── qc_warnings: per-run QC threshold breach records ──────────────────────────
CREATE TABLE IF NOT EXISTS qc_warnings (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_pk           BIGINT NOT NULL REFERENCES runs(id),
    sample_id        TEXT NOT NULL,
    overall_status   TEXT NOT NULL CHECK (overall_status IN ('warn', 'fail')),
    metric_name      TEXT NOT NULL,
    metric_value     DOUBLE PRECISION NOT NULL,
    threshold_warn   DOUBLE PRECISION NOT NULL,
    threshold_fail   DOUBLE PRECISION NOT NULL,
    threshold_source TEXT NOT NULL CHECK (threshold_source IN ('adaptive', 'bootstrap')),
    metrics_detail   JSONB,
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_qc_warnings_run ON qc_warnings(run_pk);
CREATE INDEX IF NOT EXISTS idx_qc_warnings_sample ON qc_warnings(sample_id);
CREATE INDEX IF NOT EXISTS idx_qc_warnings_metric ON qc_warnings(metric_name, recorded_at);

-- ── review_decisions: human sign-off on AI-drafted interpretations ────────────
-- Mirrors ai-report/agent/review_store.py (the SQLite-backed store used by the
-- demo). Insert-only: a changed mind is a new row, never an edit to the old one.
CREATE TABLE IF NOT EXISTS review_decisions (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_pk         BIGINT REFERENCES runs(id),
    run_id         TEXT NOT NULL,
    variant_key    TEXT NOT NULL,                    -- "chrom:pos:ref>alt"
    classification TEXT NOT NULL,
    decision       TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    reviewer       TEXT NOT NULL,
    comment        TEXT NOT NULL DEFAULT '',
    decided_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_review_variant ON review_decisions(variant_key);
CREATE INDEX IF NOT EXISTS idx_review_run ON review_decisions(run_id);

-- ── Guardrail: block UPDATE/DELETE on the immutable tables at the DB level ─────
CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Table % is insert-only (append a correction instead)', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['runs','qc_metrics','run_provenance','audit_log','qc_warnings','review_decisions'] LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trg_immutable_%1$s ON %1$s;
             CREATE TRIGGER trg_immutable_%1$s
               BEFORE UPDATE OR DELETE ON %1$s
               FOR EACH ROW EXECUTE FUNCTION forbid_mutation();', t);
    END LOOP;
END $$;

-- ── Convenience views for Metabase ────────────────────────────────────────────
CREATE OR REPLACE VIEW v_run_summary AS
SELECT r.run_id, r.sample_id, r.pipeline_version, r.caller,
       r.validation_pass, r.started_at, r.exported_at,
       EXTRACT(EPOCH FROM (r.exported_at - r.started_at))/60.0 AS turnaround_min,
       q.snp_precision, q.snp_recall, q.snp_f1,
       q.percent_duplication, q.n_variants
FROM runs r
JOIN qc_metrics q ON q.run_pk = r.id;

-- ── QC Warnings view for Metabase dashboard ───────────────────────────────────
CREATE OR REPLACE VIEW v_qc_warnings AS
SELECT w.id,
       r.run_id,
       w.sample_id,
       w.overall_status,
       w.metric_name,
       w.metric_value,
       w.threshold_warn,
       w.threshold_fail,
       w.threshold_source,
       w.recorded_at,
       r.pipeline_version,
       r.caller
FROM qc_warnings w
JOIN runs r ON r.id = w.run_pk
ORDER BY w.recorded_at DESC;

-- ── QC Warning frequency time-series (for Metabase line chart) ────────────────
CREATE OR REPLACE VIEW v_qc_warning_frequency AS
SELECT date_trunc('day', w.recorded_at) AS day,
       w.overall_status,
       w.metric_name,
       COUNT(*) AS warning_count
FROM qc_warnings w
GROUP BY day, w.overall_status, w.metric_name
ORDER BY day DESC;

-- ── QC Metric vs threshold scatter (for Metabase scatter plot) ────────────────
CREATE OR REPLACE VIEW v_qc_metric_vs_threshold AS
SELECT w.metric_name,
       w.metric_value,
       w.threshold_warn,
       w.threshold_fail,
       w.overall_status,
       w.threshold_source,
       w.recorded_at,
       w.sample_id
FROM qc_warnings w
ORDER BY w.recorded_at DESC;

-- ── Dimensional warehouse layer (star schema) ─────────────────────────────────
-- A BI-facing dimensional model over the OLTP tables above, for Metabase and
-- ad-hoc SQL analytics. Dimensions are thin views derived from the existing
-- insert-only tables — this is a warehouse *shape* over the same source of
-- truth, not a second copy that could drift from it. See ADR-0023.

CREATE OR REPLACE VIEW dim_sample AS
SELECT sample_id, reference_build, created_at
FROM samples;

-- dim_pipeline_version / dim_caller are real tables with generated identity
-- surrogate keys, not views computed on the fly: a key must stay permanent
-- once assigned, and a dense_rank()-over-live-data view can renumber
-- existing keys the moment a new distinct value sorts ahead of them.
-- Populated by an idempotent upsert — safe to re-run any time new runs may
-- have introduced a pipeline_version/caller not yet in the dimension; see
-- orchestration/airflow_dags/warehouse_etl_dag.py for where that runs on a
-- schedule.
CREATE TABLE IF NOT EXISTS dim_pipeline_version (
    pipeline_version_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_version     TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dim_caller (
    caller_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    caller     TEXT NOT NULL UNIQUE
);

INSERT INTO dim_pipeline_version (pipeline_version)
SELECT DISTINCT pipeline_version FROM runs
ON CONFLICT (pipeline_version) DO NOTHING;

INSERT INTO dim_caller (caller)
SELECT DISTINCT caller FROM runs
ON CONFLICT (caller) DO NOTHING;

CREATE OR REPLACE VIEW dim_date AS
SELECT DISTINCT date_trunc('day', started_at)::date AS date_key,
       EXTRACT(ISOYEAR FROM started_at)::int AS iso_year,
       EXTRACT(WEEK FROM started_at)::int AS iso_week,
       EXTRACT(DOW FROM started_at)::int AS day_of_week,
       trim(to_char(started_at, 'Day')) AS day_name
FROM runs
WHERE started_at IS NOT NULL;

-- fact_run: one row per pipeline run (grain = run). Materialized so Metabase
-- cards query a precomputed table rather than re-aggregating qc_warnings on
-- every dashboard load. Refreshed by the warehouse ETL job — see
-- orchestration/airflow_dags/warehouse_etl_dag.py and ADR-0023.
CREATE MATERIALIZED VIEW IF NOT EXISTS fact_run AS
SELECT
    r.id                                                      AS run_key,
    r.run_id,
    r.sample_id,
    r.pipeline_version,
    pv.pipeline_version_key,
    r.caller,
    c.caller_key,
    date_trunc('day', r.started_at)::date                     AS date_key,
    r.started_at,
    r.exported_at,
    EXTRACT(EPOCH FROM (r.exported_at - r.started_at)) / 60.0  AS turnaround_min,
    r.validation_pass,
    q.snp_precision,
    q.snp_recall,
    q.snp_f1,
    q.percent_duplication,
    q.n_variants,
    coalesce(qw.n_warn, 0)                                     AS n_warn,
    coalesce(qw.n_fail, 0)                                     AS n_fail
FROM runs r
JOIN qc_metrics q            ON q.run_pk = r.id
JOIN dim_pipeline_version pv ON pv.pipeline_version = r.pipeline_version
JOIN dim_caller c             ON c.caller = r.caller
LEFT JOIN LATERAL (
    SELECT count(*) FILTER (WHERE w.overall_status = 'warn') AS n_warn,
           count(*) FILTER (WHERE w.overall_status = 'fail') AS n_fail
    FROM qc_warnings w
    WHERE w.run_pk = r.id
) qw ON true;

CREATE UNIQUE INDEX IF NOT EXISTS idx_fact_run_key ON fact_run(run_key);
CREATE INDEX IF NOT EXISTS idx_fact_run_date ON fact_run(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_run_pipeline ON fact_run(pipeline_version_key);

-- Refresh order matters: dim_pipeline_version/dim_caller must be populated
-- (re-run the upsert above) before `REFRESH MATERIALIZED VIEW CONCURRENTLY
-- fact_run;` — otherwise a brand-new pipeline_version/caller from the
-- latest ingest has no dimension row yet and its run is silently dropped
-- by fact_run's JOIN. CONCURRENTLY needs the unique index above, and keeps
-- the view readable — no dashboard-facing lock — while it rebuilds.
