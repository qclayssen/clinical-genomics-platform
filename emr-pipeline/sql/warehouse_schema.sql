-- emr-pipeline local warehouse schema (SQLite dialect, for the runnable demo)
--
-- Mirrors db/schema.sql's design principle: staging + provenance tables are
-- INSERT-ONLY. There is no UPDATE or DELETE path in extract_and_load.py — a
-- re-extraction is a new batch, identified by extraction_batch_id, never an
-- overwrite of a previous batch's rows. Enforced here at the DB level with
-- triggers, same as the Postgres forbid_mutation() trigger in db/schema.sql
-- (SQLite has no stored-procedure trigger language, so each table gets its
-- own BEFORE UPDATE / BEFORE DELETE RAISE(ABORT, ...) pair instead of one
-- shared function).
--
-- In production this would be the Postgres warehouse layer (db/schema.sql)
-- fed by a real ODBC extraction, not a local SQLite file — see
-- emr-pipeline/README.md for the scope note.

-- ── staging_icu_admissions: one row per (admission, extraction batch) ──────────
CREATE TABLE IF NOT EXISTS staging_icu_admissions (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    extraction_batch_id    TEXT NOT NULL,
    admission_id           TEXT NOT NULL,
    mrn                    TEXT NOT NULL,
    age_years              INTEGER,
    sex                    TEXT,
    admit_datetime         TEXT NOT NULL,
    discharge_datetime     TEXT,
    unit                   TEXT NOT NULL,
    admission_source       TEXT,
    primary_diagnosis      TEXT,
    diagnosis_icd10_am     TEXT,
    apache_ii_score        INTEGER,
    ventilated             INTEGER NOT NULL DEFAULT 0,
    vasopressor_support    INTEGER NOT NULL DEFAULT 0,
    outcome                TEXT,
    length_of_stay_hours   REAL,               -- derived QC field
    loaded_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_staging_icu_batch ON staging_icu_admissions(extraction_batch_id);
CREATE INDEX IF NOT EXISTS idx_staging_icu_admission ON staging_icu_admissions(admission_id);

-- ── staging_ed_consultations: one row per (consult, extraction batch) ──────────
CREATE TABLE IF NOT EXISTS staging_ed_consultations (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    extraction_batch_id    TEXT NOT NULL,
    consult_id             TEXT NOT NULL,
    mrn                    TEXT NOT NULL,
    consult_datetime       TEXT NOT NULL,
    referring_clinician    TEXT,
    consult_note           TEXT NOT NULL,
    note_char_length       INTEGER,            -- derived QC field
    loaded_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_staging_ed_batch ON staging_ed_consultations(extraction_batch_id);

-- ── etl_provenance: one row per extraction run, mirrors run_provenance ─────────
CREATE TABLE IF NOT EXISTS etl_provenance (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    extraction_batch_id    TEXT NOT NULL UNIQUE,
    source_db_path         TEXT NOT NULL,
    git_commit             TEXT NOT NULL,
    extracted_at           TEXT NOT NULL,      -- ISO 8601 UTC
    icu_admissions_rows    INTEGER NOT NULL,
    ed_consultations_rows  INTEGER NOT NULL,
    icu_admissions_missing_fields INTEGER NOT NULL DEFAULT 0,
    extract_checksum       TEXT NOT NULL,       -- SHA-256 over the serialized extract
    dry_run                INTEGER NOT NULL DEFAULT 0
);

-- ── structured_consult_notes: LLM/rule-based extraction output, insert-only ────
CREATE TABLE IF NOT EXISTS structured_consult_notes (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    consult_id             TEXT NOT NULL,
    source_note_sha256     TEXT NOT NULL,
    presenting_complaint   TEXT,
    disposition            TEXT,
    acuity_flag            TEXT,
    diagnosis_code_guess   TEXT,
    backend                TEXT NOT NULL,       -- e.g. "offline-rule-based", "openai", "azure_foundry"
    model_id               TEXT NOT NULL,
    guardrail_banner       TEXT NOT NULL,
    requires_validation    INTEGER NOT NULL DEFAULT 1,
    extracted_at           TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_structured_notes_consult ON structured_consult_notes(consult_id);

-- ── Guardrail: block UPDATE/DELETE on the insert-only tables ────────────────────
CREATE TRIGGER IF NOT EXISTS trg_no_update_staging_icu_admissions
BEFORE UPDATE ON staging_icu_admissions
BEGIN SELECT RAISE(ABORT, 'staging_icu_admissions is insert-only (re-extract as a new batch)'); END;
CREATE TRIGGER IF NOT EXISTS trg_no_delete_staging_icu_admissions
BEFORE DELETE ON staging_icu_admissions
BEGIN SELECT RAISE(ABORT, 'staging_icu_admissions is insert-only (re-extract as a new batch)'); END;

CREATE TRIGGER IF NOT EXISTS trg_no_update_staging_ed_consultations
BEFORE UPDATE ON staging_ed_consultations
BEGIN SELECT RAISE(ABORT, 'staging_ed_consultations is insert-only (re-extract as a new batch)'); END;
CREATE TRIGGER IF NOT EXISTS trg_no_delete_staging_ed_consultations
BEFORE DELETE ON staging_ed_consultations
BEGIN SELECT RAISE(ABORT, 'staging_ed_consultations is insert-only (re-extract as a new batch)'); END;

CREATE TRIGGER IF NOT EXISTS trg_no_update_etl_provenance
BEFORE UPDATE ON etl_provenance
BEGIN SELECT RAISE(ABORT, 'etl_provenance is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_no_delete_etl_provenance
BEFORE DELETE ON etl_provenance
BEGIN SELECT RAISE(ABORT, 'etl_provenance is insert-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_no_update_structured_consult_notes
BEFORE UPDATE ON structured_consult_notes
BEGIN SELECT RAISE(ABORT, 'structured_consult_notes is insert-only (a corrected extraction is a new row)'); END;
CREATE TRIGGER IF NOT EXISTS trg_no_delete_structured_consult_notes
BEFORE DELETE ON structured_consult_notes
BEGIN SELECT RAISE(ABORT, 'structured_consult_notes is insert-only (a corrected extraction is a new row)'); END;
