# ADR-0029 — `emr-pipeline/`: an EMR/ICU/VVED data-engineering demo module

**Status:** Accepted · **Date:** 2026-09-10

## Context

This platform demonstrates germline SNV variant-calling data-engineering patterns —
insert-only provenance, ADR-driven design, AI guardrails — scoped to GIAB HG002 chr20
(ADR-0001). Those same patterns are directly relevant to a different, real class of clinical
data work: an ICU / Virtual Emergency Department (VVED) research data team's day-to-day —
SQL/ETL extraction from an EMR via ODBC, a local warehouse feeding a structured clinical data
repository, routine submission to a national ICU outcomes registry (ANZICS's Adult Patient
Database), and using LLM APIs to extract structured, codified data from unstructured ED/ICU
consultation notes. None of that is genomics, and none of it belongs bolted onto the existing
pipeline, API, or AI-report code — but demonstrating it *using this repo's established
conventions* is a legitimate, additive use of the same portfolio.

## Decision

Add a new top-level `emr-pipeline/` module, entirely separate from `pipeline/`, `api/`, `web/`,
`ai-report/`, and `infra/` (only a read-only import from `ai-report/agent/llm.py`):

- **`mock_emr/build_mock_emr.py`** fabricates a tiny synthetic SQLite "EMR" — `icu_admissions`
  and `ed_consultations` tables, ~15-20 clearly-fake rows (`TESTPATIENT, ...` names, `MOCK-...`
  MRNs). Stands in for what a real ODBC-connected EMR reporting database looks like; the
  extraction code carries an explicit `# production would use: pyodbc.connect(...)` comment
  at the exact point a real driver would plug in.
- **`etl/extract_and_load.py`** is a pandas/sqlite3 ETL: extract, compute derived QC fields
  (length of stay, missing-field counts), and load into a local warehouse using the same
  insert-only philosophy as `db/schema.sql` (ADR-0005) — `sql/warehouse_schema.sql` defines
  staging + provenance tables with SQLite triggers blocking `UPDATE`/`DELETE`, and every load
  writes a provenance row (extraction timestamp, source row counts, a checksum of the extract,
  git commit), mirroring `pipeline/bin/build_metrics.py`. Supports `--dry-run`.
- **`llm/structure_consult_notes.py`** extracts structured fields (presenting complaint,
  disposition, acuity flag, an ICD-10-AM-style diagnosis code guess) from the free-text
  `consult_note` column, reusing `ai-report/agent/llm.py`'s existing multi-provider backend
  abstraction rather than forking it. Every output — offline or model-backed — passes through
  `enforce_extraction_guardrails()`: a mandatory `AI-EXTRACTED — REQUIRES CLINICIAN VALIDATION`
  banner, a provenance line (backend, model, timestamp, sha256 of the source note), and an
  advice-phrase scrub, mirroring `ai-report/infer.py`'s `enforce_guardrails()` (ADR-0008). An
  `--offline` deterministic keyword-based extractor is the default so the demo never requires
  an API key; any real backend falls back to it on error, exactly like `infer.py` falls back to
  `render_offline()`.
- **`registry/anzics_export.py`** maps warehouse ICU admissions to a documented *subset* of
  ANZICS-APD-style fields and validates them (required-field checks, range checks — e.g.
  APACHE II must fall in the published 0-71 range), emitting a CSV/JSON extract plus a
  validation report. Explicitly not a conformant APD implementation, stated in the module
  docstring — the same honesty pattern ADR-0028 used for the FHIR intake subset.
- Tests in `tests/test_emr_pipeline.py`, run under plain `pytest`, no external services —
  consistent with how every other Python component in this repo is tested.

## What's explicitly out of scope

- **Real EMR/ODBC connectivity.** No real connection string, no real hospital system. The
  `pyodbc` swap point is documented, not implemented.
- **Real ANZICS submission.** No real APD data dictionary, no real submission mechanism or
  credentials, no claim of registry conformance.
- **Real PHI.** Every row in `mock_emr/` is synthetic and obviously so by construction (fixed
  fake names/MRN prefixes), never sourced from any real record.
- **A production-grade clinical NLP/coding engine.** The offline extractor is keyword/regex
  matching; the diagnosis-code map is a small illustrative set, not a coding reference.

## Consequences

**Good**
- Demonstrates the exact skill set a hospital ICU/VVED data role JD asks for
  (ODBC-shaped extraction → warehouse → registry export, LLM-assisted note structuring) using
  real, runnable code rather than a bullet point on a resume.
- Reuses this repo's hardest-won conventions (insert-only + triggers, provenance stamping,
  guardrails, the LLM backend abstraction) instead of inventing a parallel, weaker pattern —
  the same discipline this repo already holds itself to.
- Fully additive: `pipeline/`, `api/`, `web/`, `ai-report/` (besides the one read-only import),
  and `infra/` are untouched; nothing here can regress the genomics platform's CI or guardrails.

**Bad / accepted limitations**
- The offline extractor's keyword matching is intentionally simple and will misclassify or
  return `"unknown"` for notes outside its hand-written keyword set — acceptable for a
  demo of the *pattern*, not for a claim of clinical NLP accuracy.
- `sql/warehouse_schema.sql` is SQLite (matching `mock_emr`'s zero-setup goal), not the Postgres
  dialect `db/schema.sql` uses in production — the file says so; a real deployment would port
  the same insert-only design to Postgres, not use SQLite as a warehouse.
- No dashboard/orchestration layer (no Metabase card, no Airflow DAG) for `emr-pipeline/` — out
  of scope for this ADR; could be a follow-up ADR if useful.

## Alternatives considered

- **Extending `db/schema.sql` / `pipeline/` directly with ICU tables** — rejected: mixes two
  unrelated clinical domains (germline SNV genomics vs. ICU outcomes) in one schema and one
  pipeline, defeating the "scoped, coherent platform" value of ADR-0001.
- **A synthetic-data generator library (e.g. Faker) for `mock_emr/`** — rejected as an
  unnecessary new dependency; ~30 hand-written rows are enough to exercise every code path and
  keep the module's only import surface `pandas` + stdlib.
- **Pydantic models for the structured-note schema** — considered, since `api/` already depends
  on pydantic; used a plain `dataclass` instead (`StructuredConsultNote`) to keep `llm/` free of
  new dependencies, consistent with how `ai-report/agent/llm.py`'s own `Message`/`LLMResponse`
  types are plain dataclasses.
