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

-- ── Guardrail: block UPDATE/DELETE on the immutable tables at the DB level ─────
CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Table % is insert-only (append a correction instead)', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['runs','qc_metrics','run_provenance','audit_log','qc_warnings'] LOOP
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
