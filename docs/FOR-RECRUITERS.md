# For Recruiters & Hiring Managers

A one-page map of what this project demonstrates and where to look. If you have three
minutes, read this and skim the [architecture diagram](../README.md#architecture).

## What it is

An end-to-end **clinical-grade genomics platform** (portfolio scale): raw DNA sequencing data
→ QC → variant calling → **accuracy benchmarked against a gold-standard truth set** →
provenance-tracked database → operations dashboard → a **fine-tuned LLM** that drafts
plain-language summaries under enforced human-review guardrails.

Built solo, deliberately scoped ([ADR-0001](adr/0001-scope-giab-hg002-chr20.md)) so it's
finished and runnable, not a half-built sprawl.

## Skills demonstrated, with evidence

| Skill area | What's shown | Where |
|---|---|---|
| **Bioinformatics pipelines** | Nextflow DSL2, nf-core style, 11 modules, QC→align→call→validate | `pipeline/` |
| **Analytical validation** | `hap.py` vs GIAB truth; precision/recall/F1; explicit acceptance criterion | `pipeline/modules/validate/`, `docs/VALIDATION.md` |
| **Cloud / IaC** | AWS CDK (TypeScript), 4 stacks, Batch/Fargate, least-privilege IAM, CloudWatch | `infra/` |
| **Data engineering** | Insert-only Postgres schema, provenance + audit trail, migrations | `db/` |
| **BI / reporting** | Metabase dashboard defined as version-controlled SQL | `dashboards/` |
| **Machine learning** | **PyTorch** QLoRA fine-tuning of a small open LLM; model card; guardrails | `ai-report/`, `ai-report/MODEL_CARD.md` |
| **MLOps / responsible AI** | Human-in-the-loop, enforced guardrails in code, graceful degradation | [ADR-0008](adr/0008-guardrails-human-in-the-loop.md) |
| **DevOps** | Docker per step (pinned by digest), GitHub Actions CI (pipeline + infra + ML) | `docker/`, `.github/workflows/` |
| **Engineering judgement** | 9 Architecture Decision Records weighing trade-offs | `docs/adr/` |
| **Quality/accreditation literacy** | ISO 15189 / NATA patterns: validation, provenance, SOP, change control | `docs/VALIDATION.md`, `docs/SOP-run-pipeline.md` |

## The ML component, specifically

Since AI/ML is increasingly expected, here's the honest shape of it:

- **It's real PyTorch fine-tuning**, not just calling an API — `transformers` + `peft` + `trl`
  (QLoRA). See [ADR-0007](adr/0007-qlora-small-open-model.md) and the
  [Model Card](../ai-report/MODEL_CARD.md).
- **It's runnable without a GPU.** `train_smoke.py` runs the identical LoRA training loop on a
  tiny model in ~1 minute — verified, and wired into CI.
- **It's responsible by construction.** Every output carries a mandatory review banner and
  field citations, enforced in tested code, not left to the model
  ([ADR-0008](adr/0008-guardrails-human-in-the-loop.md)).

## What was actually run vs. what needs a full environment

Being straight about this (it's a portfolio, not a live service):

- ✅ **Verified running:** the metrics/provenance builder, the offline report renderer, the
  CPU LoRA fine-tuning smoke test, and the unit-test suite.
- ⏳ **Needs Nextflow + Docker:** the full genomics pipeline on real GIAB data.
- ⏳ **Needs an AWS account:** `cdk deploy` of the infrastructure (CI runs `cdk synth`).
- ⏳ **Needs a GPU:** full QLoRA fine-tune of the 3B model (CPU smoke test proves the loop).

Status is tracked honestly in [docs/MILESTONES.md](MILESTONES.md).

## Suggested reading order

1. [README](../README.md) — architecture + quickstart
2. This page
3. [Beginner's Guide](BEGINNERS-GUIDE.md) + [Glossary](GLOSSARY.md) — if the domain is new
4. [ADRs](adr/) — the engineering-judgement story
5. [Model Card](../ai-report/MODEL_CARD.md) + [VALIDATION](VALIDATION.md) — the rigor
