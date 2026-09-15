# emr-pipeline — ICU / Virtual ED (VVED) data-engineering demo

> New to any of the abbreviations below (EMR, ODBC, ETL, ANZICS APD, LOS, MRN...)?
> Every one is explained in plain English in
> [docs/GLOSSARY.md §12](../docs/GLOSSARY.md#12-emr--icu--registry-demo-emr-pipeline).

A small, self-contained module demonstrating the EMR-to-registry data-engineering
patterns used in ICU / Virtual Emergency Department (VVED) research data teams.

**In plain English:** hospitals keep patient records in a system called an **EMR**
(Electronic Medical Record) — think of it as their central filing cabinet. This demo
shows the standard way a research data team pulls data *out* of that filing cabinet,
cleans it up, and turns it into a report a national quality registry expects, without
ever touching a real hospital or a real patient:

**Step 1 — pull the data out** (`mock_emr/` → `etl/`): connect to the record system
via **ODBC** (a universal, vendor-neutral way to talk to any hospital's database — like
a universal power adapter that works no matter which country/socket you're in), extract
the raw rows, and load them into a local database that never allows edits or deletes
(**insert-only** — see below).

**Step 2 — make sense of free text** (`llm/`): consult notes are messy paragraphs
written by clinicians. An LLM (AI language model) reads each note and pulls out a few
structured fields (why the patient came in, how urgent it was, what happened next) —
always labeled as AI-generated and requiring a human's sign-off before anyone relies on it.

**Step 3 — export to a registry** (`registry/`): reshape the cleaned data into the field
layout a real ICU quality registry (**ANZICS APD**, in Australia/NZ) expects, and check
it for mistakes before "submitting" it (this demo never actually submits anywhere).

It is scoped separately from the rest of this repo (the germline SNV genomics
platform — DNA variant calling) but deliberately **reuses** this repo's existing,
load-bearing patterns rather than reinventing them:

- **Insert-only warehouse tables + immutability triggers** — the database physically
  *rejects* any UPDATE or DELETE on results/provenance tables; a correction is always a
  new row, never an edit to an old one (so there's always a full history of what was
  known and when). Modeled on [`db/schema.sql`](../db/schema.sql)
  (see [ADR-0005](../docs/adr/0005-insert-only-postgres.md)).
- **Provenance stamping** — every load is tagged with *where it came from and how it was
  produced*: git commit, extraction timestamp, source row counts, and a checksum
  (a short fingerprint that changes if even one byte of the data changes, used to detect
  tampering or corruption). Modeled on
  [`pipeline/bin/build_metrics.py`](../pipeline/bin/build_metrics.py).
- **AI guardrails** — every LLM-structured output automatically gets a mandatory
  "AI-generated, needs human review" banner, a provenance line, and a scrub for
  overconfident medical-advice phrasing, so it can never be mistaken for a finished,
  clinician-approved result. Modeled on [`ai-report/infer.py`](../ai-report/infer.py)'s
  `enforce_guardrails()` (see [ADR-0008](../docs/adr/0008-guardrails-human-in-the-loop.md)).
- **The multi-provider LLM backend abstraction**
  ([`ai-report/agent/llm.py`](../ai-report/agent/llm.py)) — one shared piece of code
  that can talk to several different AI providers (Ollama running locally, OpenAI,
  Anthropic, Azure AI Foundry, AWS Bedrock) through the same interface, so swapping
  providers is a config change, not a rewrite. It is imported here, not forked, so all
  of those backends work for free.

See [`docs/adr/0029-emr-icu-vved-demo-module.md`](../docs/adr/0029-emr-icu-vved-demo-module.md)
for the full rationale and explicit out-of-scope list.

## What this is NOT

- **Not connected to a real EMR.** There is no real ODBC connection (the hospital
  database link), no real hospital system, and no real PHI (Protected Health
  Information — any data that could identify a real patient) anywhere in this module.
  `mock_emr/` fabricates a tiny SQLite (a simple, file-based database — no server needed)
  database with ~15–20 clearly-synthetic rows (fake names like `TESTPATIENT, Alpha`,
  fake MRNs — Medical Record Numbers — prefixed `MOCK-`).
- **Not a real ANZICS submission.** `registry/anzics_export.py` maps warehouse
  data into a *documented subset* of ANZICS APD-style fields (the Australian/NZ
  intensive-care registry's data format) to demonstrate the field-mapping + validation
  pattern — it is not the real APD data dictionary, and nothing here is submitted anywhere.
- **Not a certified clinical NLP tool.** NLP (Natural Language Processing) here means
  the LLM reading free-text notes. `llm/structure_consult_notes.py` extracts a handful
  of fields from that text for a research warehouse demo; every output is flagged
  `AI-EXTRACTED — REQUIRES CLINICIAN VALIDATION` and is not fit for any clinical or
  coding decision without human review.

## Layout

| Path | What's here (plain English) |
|---|---|
| `mock_emr/build_mock_emr.py` | Builds a fake, synthetic "hospital database" (SQLite — a simple file-based database) standing in for a real EMR: two tables, `icu_admissions` (ICU stays) and `ed_consultations` (ER visits), ~15–20 made-up rows |
| `etl/extract_and_load.py` | The ETL script: pulls the fake rows out (**extract**), computes things like length-of-stay and flags missing fields (**transform**), then writes them into `warehouse.db` in a way that can never be edited or deleted (**insert-only load**), stamping each batch with a provenance record |
| `sql/warehouse_schema.sql` | The database table definitions for that insert-only warehouse (written for SQLite here so the demo needs no setup; the file notes what the Postgres/production version would look like) |
| `llm/structure_consult_notes.py` | Reads each messy, free-text consult note and pulls out four structured fields: `presenting_complaint` (why they came in), `disposition` (what happened next), `acuity_flag` (how urgent), `diagnosis_code_guess` (a guessed diagnosis code) — via the shared `ai-report/agent/llm.py` AI backend, with a deterministic (no-AI, rule-based, always-the-same-answer) `--offline` fallback |
| `llm/prompt_template.md` | The instructions ("prompt") given to the AI model when extracting those fields in non-offline mode |
| `registry/anzics_export.py` | Reshapes the warehouse's ICU admissions into a stub (simplified, demo-only) ANZICS-APD-style CSV/JSON export, plus a validation report checking for errors — including admission source and elective-vs-emergency status, fields real ICU registries use to compare hospitals' **casemix** (patient mix and severity) fairly |

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

**In plain English:** everything above talks to a fake, local database. This section
proves the *same code* also works over a real **ODBC** connection — the standard,
vendor-neutral protocol real hospital EMR systems are queried through — without
needing an actual hospital to test against.

By default `etl/extract_and_load.py`'s `_connect()` uses `sqlite3` (Python's built-in,
no-install-needed database library) purely so this demo runs with zero setup. Setting
the `EMR_ODBC_DSN` environment variable (the connection string — driver, server,
database, credentials — see the Glossary's **DSN** entry) switches it to a genuine
`pyodbc` connection instead — this is not a comment describing what production would
do, it's a real, working code path (`_connect_odbc()`).

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
