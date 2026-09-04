# CLAUDE.md — Clinical Genomics Insight Platform

Onboarding for coding agents. Keep it factual; link to `docs/` rather than duplicating.

## What this is

A portfolio, end-to-end **germline SNV** variant-calling platform: raw WGS reads → QC →
alignment → variant calling → **benchmarked against a GIAB truth set with `hap.py`** →
provenance-stamped results in insert-only Postgres → Metabase ops dashboard → a QLoRA
fine-tuned LLM that drafts a plain-language summary under enforced human-review guardrails.
Deliberately scoped to **GIAB HG002 / NA24385, GRCh38 chr20** ([ADR-0001](docs/adr/0001-scope-giab-hg002-chr20.md))
so one person can finish it. It demonstrates the validation and traceability *patterns* ISO
15189 / NATA accreditation asks for — it is **not** an accredited clinical test and must not
be used for clinical decisions (see the scope-honesty note in [README.md](README.md)).

## Repo map (one line per top-level dir)

| Path | What's here |
|---|---|
| `pipeline/` | Nextflow DSL2 pipeline: `main.nf`, `nextflow.config`, 12 one-process modules under `modules/`, helper scripts in `bin/`, `assets/`, `conf/` |
| `infra/` | AWS CDK (TypeScript) app: 4 stacks in `lib/`, wired in `bin/app.ts`, guardrail tests in `test/` |
| `db/` | Postgres `schema.sql` (insert-only tables + immutability triggers, star-schema warehouse layer), migrations, seed |
| `dashboards/metabase/` | Version-controlled Metabase dashboard + question/SQL definitions |
| `api/` | FastAPI REST service over run/QC/provenance data, with OpenAPI docs (`/docs`, `/redoc`); fixture-backed by default, optional `CGP_DB_URL` for Postgres |
| `orchestration/` | Illustrative Airflow DAG scheduling the warehouse ETL/refresh (design note, see ADR-0023) |
| `ai-report/` | PyTorch QLoRA fine-tune + inference (`infer.py`, `train_lora.py`, `train_smoke.py`, `make_dataset.py`), `MODEL_CARD.md` |
| `docker/` | One pinned Dockerfile per stage plus `Dockerfile.tools` for the helper scripts |
| `docs/` | Beginner's guide, glossary, `VALIDATION.md`, `SOP-run-pipeline.md`, `MILESTONES.md`, `FOR-RECRUITERS.md` |
| `docs/adr/` | 23 Architecture Decision Records (append-only); see `README.md` there for the index |
| `tests/` | Python unit tests + small committed fixtures in `tests/fixtures/` |
| `.github/workflows/` | CI: nf-core-style config check, pipeline test profile, CDK synth, ML smoke test |

## How to run the runnable parts

These run with no GPU, no AWS, and no bioinformatics tools installed. Run from the repo root
unless noted.

```bash
# Refresh the Metabase warehouse layer (star schema over runs/qc_metrics)
# after loading db/schema.sql + db/seed_demo.sql — see dashboards/metabase/README.md
psql "$CGP_DB_URL" -c "
  INSERT INTO dim_pipeline_version (pipeline_version)
  SELECT DISTINCT pipeline_version FROM runs ON CONFLICT (pipeline_version) DO NOTHING;
  INSERT INTO dim_caller (caller)
  SELECT DISTINCT caller FROM runs ON CONFLICT (caller) DO NOTHING;
"
psql "$CGP_DB_URL" -c "REFRESH MATERIALIZED VIEW fact_run;"

# Python unit tests (provenance + guardrail logic; dependency-free)
pytest

# REST API with OpenAPI docs — fixture-backed, no DB/AWS needed
pip install -r api/requirements.txt
uvicorn api.main:app --reload   # then open http://127.0.0.1:8000/docs

# Deterministic offline report renderer (no ML deps at all)
python3 ai-report/infer.py --metrics tests/fixtures/HG002_chr20.metrics.json --offline

# CPU LoRA smoke test — the identical fine-tuning loop on a tiny model, ~1 min
# (needs: pip install torch transformers datasets peft — CPU wheels are fine)
python ai-report/train_smoke.py

# Pipeline stub DAG — validates structure without real data/tools (needs Nextflow + Docker)
cd pipeline && nextflow run main.nf -profile test,docker -stub
```

CDK: `cd infra && npm ci && npm test` runs the guardrail tests; `npx cdk synth` builds
templates without an AWS account.

## Non-negotiable design rules

- **Insert-only results/provenance.** `runs`, `qc_metrics`, `run_provenance`, `audit_log` are
  append-only; DB triggers (`forbid_mutation()`) reject UPDATE/DELETE. A correction is a *new*
  run row, never an edit. ([db/schema.sql](db/schema.sql), [ADR-0005](docs/adr/0005-insert-only-postgres.md))
- **Every result carries a provenance stamp.** Git commit, pipeline/tool/reference/truth-set
  versions, and SHA-256 checksums of all inputs — built into `metrics.json` by
  `pipeline/bin/build_metrics.py` and threaded from `main.nf`. Never remove fields from it.
- **AI output always passes `enforce_guardrails()`** ([ai-report/infer.py](ai-report/infer.py)):
  mandatory `AI-DRAFTED — REQUIRES CLINICIAN REVIEW` banner, provenance line, and advice-phrase
  scrubbing — then a human signs off. The model only ever sees `metrics.json`, never raw reads
  or the VCF body. ([ADR-0008](docs/adr/0008-guardrails-human-in-the-loop.md))
- **Decisions are ADRs, append-only.** Record a new choice as the next-numbered file in
  `docs/adr/`; never rewrite an old one — supersede it and update its status.
- **Re-validate on change.** Any change to reference, caller, or filtering re-triggers the
  `hap.py`-vs-GIAB validation before tagging. Acceptance criterion: **SNV F1 ≥ 0.99**.
  ([docs/VALIDATION.md](docs/VALIDATION.md), [ADR-0003](docs/adr/0003-truth-set-validation.md))

## Conventions

- **One process per module file**, nf-core style (`pipeline/modules/<group>/<tool>.nf`). Every
  process has a `stub:` block so `-stub` runs offline, and a `container` directive.
- **Pin Docker images by digest** (`@sha256:…`) in production; Biocontainers where available.
  Container identity is captured in provenance. ([ADR-0009](docs/adr/0009-docker-pinned-by-digest.md))
- **CDK guardrail tests must stay green** — they encode accreditation-relevant invariants
  (bucket versioning, public-access block, TLS-only, IAM deny-delete on raw/results). See
  `infra/test/stacks.test.ts`.
- **Change behaviour → update tests + provenance** in the same change. Python logic is covered
  by `tests/test_build_metrics.py`.

## Verified vs. needs-environment

- **Verified running:** `pytest` suite, the metrics/provenance builder, `infer.py --offline`,
  the CPU LoRA smoke test (`train_smoke.py`), and the FastAPI service (`uvicorn api.main:app`,
  fixture-backed by default).
- **Needs Nextflow + Docker:** the full genomics pipeline on real GIAB data.
- **Needs an AWS account:** `cdk deploy` (CI only runs `cdk synth`).
- **Needs a GPU:** the full QLoRA fine-tune of the 3B model (the CPU smoke test proves the loop).

Status is tracked honestly in [docs/MILESTONES.md](docs/MILESTONES.md). This is a portfolio
project, not a certified clinical device.
