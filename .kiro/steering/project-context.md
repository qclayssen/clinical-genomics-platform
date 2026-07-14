# Clinical Genomics Insight Platform — Project Context

Onboarding for coding agents. Keep it factual; link to `docs/` rather than duplicating.

## What this is

A portfolio, end-to-end **germline SNV** variant-calling platform: raw WGS reads → QC →
alignment → variant calling → **benchmarked against a GIAB truth set with `hap.py`** →
provenance-stamped results in insert-only Postgres → Metabase ops dashboard → a QLoRA
fine-tuned LLM that drafts a plain-language summary under enforced human-review guardrails.
Deliberately scoped to **GIAB HG002 / NA24385, GRCh38 chr20** so one person can finish it.

## Repo map

| Path | What's here |
|---|---|
| `pipeline/` | Nextflow DSL2 pipeline: `main.nf`, `nextflow.config`, modules under `modules/`, helper scripts in `bin/`, `assets/`, `conf/` |
| `infra/` | AWS CDK (TypeScript) app: 4 stacks in `lib/`, wired in `bin/app.ts`, guardrail tests in `test/` |
| `db/` | Postgres `schema.sql` (insert-only tables + immutability triggers), migrations, seed |
| `dashboards/metabase/` | Version-controlled Metabase dashboard + question/SQL definitions |
| `ai-report/` | PyTorch QLoRA fine-tune + inference (`infer.py`, `train_lora.py`, `train_smoke.py`, `make_dataset.py`), `MODEL_CARD.md` |
| `docker/` | One pinned Dockerfile per stage plus `Dockerfile.tools` for helper scripts |
| `docs/` | Beginner's guide, glossary, `VALIDATION.md`, `SOP-run-pipeline.md`, `MILESTONES.md` |
| `docs/adr/` | Architecture Decision Records (append-only) |
| `tests/` | Python unit tests + small committed fixtures in `tests/fixtures/` |
| `.github/workflows/` | CI: nf-core lint, pipeline test profile, CDK synth, ML smoke test |

## How to run

```bash
# Python unit tests (provenance + guardrail logic; dependency-free)
pytest

# Deterministic offline report renderer (no ML deps at all)
python3 ai-report/infer.py --metrics tests/fixtures/HG002_chr20.metrics.json --offline

# CPU LoRA smoke test (~1 min, needs: pip install torch transformers datasets peft)
python ai-report/train_smoke.py

# Pipeline stub DAG (needs Nextflow + Docker)
cd pipeline && nextflow run main.nf -profile test,docker -stub
```

CDK: `cd infra && npm ci && npm test` runs guardrail tests; `npx cdk synth` builds templates.
