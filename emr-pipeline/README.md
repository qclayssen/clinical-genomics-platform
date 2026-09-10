# emr-pipeline — ICU / Virtual ED (VVED) data-engineering demo

A small, self-contained module demonstrating the EMR-to-registry data-engineering
patterns used in ICU / Virtual Emergency Department (VVED) research data teams:
**EMR extraction (ODBC-shaped) → local warehouse (insert-only) → LLM-assisted
structuring of free-text consult notes → registry (ANZICS APD-style) export with
validation.**

It is scoped separately from the rest of this repo (the germline SNV genomics
platform) but deliberately **reuses** this repo's existing, load-bearing patterns
rather than reinventing them:

- **Insert-only warehouse tables + immutability triggers**, modeled on
  [`db/schema.sql`](../db/schema.sql) (see [ADR-0005](../docs/adr/0005-insert-only-postgres.md)).
- **Provenance stamping** (git commit, extraction timestamp, source row counts,
  a checksum of the extract) written alongside every load, modeled on
  [`pipeline/bin/build_metrics.py`](../pipeline/bin/build_metrics.py).
- **AI guardrails** (mandatory banner + provenance line + advice-phrase scrub,
  human-review-required by construction) on every LLM-structured output,
  modeled on [`ai-report/infer.py`](../ai-report/infer.py)'s `enforce_guardrails()`
  (see [ADR-0008](../docs/adr/0008-guardrails-human-in-the-loop.md)).
- **The multi-provider LLM backend abstraction**
  ([`ai-report/agent/llm.py`](../ai-report/agent/llm.py)) is imported, not forked,
  so Ollama/OpenAI/Anthropic/Azure AI Foundry/AWS Bedrock all work here for free.

See [`docs/adr/0029-emr-icu-vved-demo-module.md`](../docs/adr/0029-emr-icu-vved-demo-module.md)
for the full rationale and explicit out-of-scope list.

## What this is NOT

- **Not connected to a real EMR.** There is no real ODBC connection, no real
  hospital system, and no real PHI anywhere in this module. `mock_emr/` fabricates
  a tiny SQLite database with ~15–20 clearly-synthetic rows (fake names like
  `TESTPATIENT, Alpha`, fake MRNs prefixed `MOCK-`).
- **Not a real ANZICS submission.** `registry/anzics_export.py` maps warehouse
  data into a *documented subset* of ANZICS APD-style fields to demonstrate the
  field-mapping + validation pattern — it is not the real APD data dictionary,
  and nothing here is submitted anywhere.
- **Not a certified clinical NLP tool.** `llm/structure_consult_notes.py` extracts
  a handful of fields from free text for a research warehouse demo; every output
  is flagged `AI-EXTRACTED — REQUIRES CLINICIAN VALIDATION` and is not fit for any
  clinical or coding decision without human review.

## Layout

| Path | What's here |
|---|---|
| `mock_emr/build_mock_emr.py` | Builds a synthetic SQLite "EMR": `icu_admissions` + `ed_consultations` tables, ~15–20 fake rows |
| `etl/extract_and_load.py` | pandas/sqlite3 ETL: extract → transform (LOS, missing-field QC) → insert-only load into `warehouse.db`, with a provenance row per extraction batch |
| `sql/warehouse_schema.sql` | Insert-only staging + provenance tables (SQLite dialect for this runnable demo; see the note in the file for the Postgres-production equivalent) |
| `llm/structure_consult_notes.py` | Structures free-text `consult_note` rows into `presenting_complaint` / `disposition` / `acuity_flag` / `diagnosis_code_guess`, via `ai-report/agent/llm.py`, with a deterministic `--offline` fallback |
| `llm/prompt_template.md` | The extraction prompt used in non-offline mode |
| `registry/anzics_export.py` | Maps warehouse ICU admissions to a stub ANZICS-APD-style CSV/JSON export + validation report (incl. admission source / elective-vs-emergency, a field ICU registries commonly report for casemix) |

## Running it

No credentials, no Docker, no AWS. From the repo root:

```bash
# 1. Build the synthetic EMR (SQLite)
python3 emr-pipeline/mock_emr/build_mock_emr.py

# 2. Extract + transform + load into the local insert-only warehouse
python3 emr-pipeline/etl/extract_and_load.py
#   (or --dry-run to see the provenance stamp without writing anything)

# 3. Structure the ED consult notes (offline, deterministic, no API key)
python3 emr-pipeline/llm/structure_consult_notes.py --offline

# 4. Export a stub ANZICS-APD-style extract + validation report
python3 emr-pipeline/registry/anzics_export.py

# Tests
pytest tests/test_emr_pipeline.py
```

To point `structure_consult_notes.py` at a real LLM backend instead of the
offline rule-based extractor: `--backend openai` (needs `OPENAI_API_KEY`),
`--backend azure_foundry`, `--backend bedrock`, etc. — any backend name
`ai-report/agent/llm.py` supports. The offline path stays the default so the
demo never requires credentials.

## From mock ODBC to a real EMR — and a real, verified ODBC connection

By default `etl/extract_and_load.py`'s `_connect()` uses `sqlite3` (stdlib)
purely so this demo runs with zero setup. Setting the `EMR_ODBC_DSN`
environment variable switches it to a genuine `pyodbc` connection instead —
this is not a comment describing what production would do, it's a real,
working code path (`_connect_odbc()`).

That path has actually been run and verified, not just written:

```bash
brew install unixodbc sqliteodbc   # driver manager + a real ODBC driver
pip install pyodbc

# register the driver once (see odbcinst -j for the config path it prints)
cat >> "$(odbcinst -j | awk -F': ' '/DRIVERS/{print $2}')" <<'EOF'

[SQLite3]
Description = SQLite3 ODBC Driver
Driver      = /opt/homebrew/Cellar/sqliteodbc/<version>/lib/libsqlite3odbc.dylib
EOF

EMR_ODBC_DSN="DRIVER=SQLite3;DATABASE=$(pwd)/emr-pipeline/mock_emr/mock_emr.db" \
  python3 emr-pipeline/etl/extract_and_load.py --dry-run
```

That command extracts the same 18 ICU admissions / 15 ED consultations
through a real `pyodbc.connect()` → ODBC driver manager → SQLite ODBC driver
round trip, and produces a byte-identical `extract_checksum` to the direct
sqlite3 path — proven automatically by
`tests/test_emr_pipeline.py::test_extract_via_real_odbc_matches_direct_sqlite_extract`
(skipped, not failed, on a machine without the driver installed).

**What this does and doesn't prove:** it's a real ODBC round trip against a
real ODBC driver — genuine `pyodbc` experience, not a paraphrase of the
pyodbc docs. It is *not* a connection to a real hospital EMR (Cerner/EPIC/iPM
etc.) — that would need real network access, credentials, and a live
reporting database this repo has no way to reach. A hospital connection
changes the DSN's `DRIVER=`/`SERVER=`/`DATABASE=`/credentials; the connection
object returned, and everything downstream of it (`extract()`, the pandas
transforms, provenance stamping, insert-only load), is unchanged either way —
that's the whole point of `_connect()` being the single place this differs.
