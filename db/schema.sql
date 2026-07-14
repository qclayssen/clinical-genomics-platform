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

-- ── Guardrail: block UPDATE/DELETE on the immutable tables at the DB level ─────
CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Table % is insert-only (append a correction instead)', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['runs','qc_metrics','run_provenance','audit_log'] LOOP
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
