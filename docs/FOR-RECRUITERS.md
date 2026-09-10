<!-- markdownlint-configure-file { "MD013": { "line_length": 120 }, "MD033": false }
     doc-index: skills=[bioinformatics, AWS CDK, data engineering, applied ML, agentic AI,
     multi-cloud LLM integration (Azure AI Foundry, AWS Bedrock), FHIR/HL7 intake, REST API + React];
     scope: complete solo-built platform; validation: ISO 15189 patterns, hap.py benchmarking;
     delivery: autonomous, end-to-end, 28 architecture decision records documenting trade-offs. -->

# For Recruiters & Hiring Managers

**Author: Quentin Clayssen** — solo-built, AI-orchestrated, end-to-end.

A one-page map of what this project demonstrates and where to look. If you have three
minutes, read this and skim the [architecture diagram](../README.md#architecture).

## What it is

An end-to-end **clinical-grade genomics platform** (portfolio scale): raw DNA sequencing data
→ QC → variant calling → **accuracy benchmarked against a gold-standard truth set** →
provenance-tracked database → operations dashboard → a **fine-tuned LLM** that drafts
plain-language summaries under enforced human-review guardrails.

Built solo, deliberately scoped ([ADR-0001](adr/0001-scope-giab-hg002-chr20.md)) so it's
finished and runnable, not a half-built sprawl.

## Reading this as a data-engineering / BI project

The domain is genomics, but nothing here requires a genomics background to build or extend —
the same way a hospital's billing warehouse or a lab's LIMS integration doesn't. If you're
screening for a **data engineer / analytics engineer / BI developer** role, here's the same
project translated into that vocabulary:

| This project has... | ...which is really | Where |
|---|---|---|
| A Nextflow pipeline writing `runs`/`qc_metrics`/`qc_warnings` | An ETL/ELT pipeline landing operational events from a source system into a warehouse | `pipeline/`, `db/schema.sql` |
| Insert-only Postgres + immutability triggers | Data-quality/integrity guarantees on the warehouse (no silent overwrites, full history) | `db/schema.sql`, [ADR-0005](adr/0005-insert-only-postgres.md) |
| `dim_pipeline_version`/`dim_caller`/`dim_date` + `fact_run` | A hand-designed star schema, refreshed on a schedule | `db/schema.sql`, [ADR-0023](adr/0023-star-schema-warehouse-airflow.md) |
| The same star schema, rebuilt with dbt | Staged sources → `ref()`-linked models → 38 schema tests → generated docs — the analytics-engineering toolchain | `dbt/`, [ADR-0025](adr/0025-dbt-analytics-engineering-layer.md) |
| An Airflow DAG that actually runs (not just described) | Scheduled orchestration of the extract/load + warehouse-refresh steps, demoable with `docker compose` | `orchestration/`, [ADR-0026](adr/0026-runnable-airflow-demo.md) |
| Two Metabase dashboards, defined as version-controlled SQL + provisioned via a REST API script | "Dashboards as code" — no click-built, unreproducible dashboards | `dashboards/metabase/`, screenshots in the [root README](../README.md#dashboard-preview) |
| Postgres role-based row sandboxing (`db/sandboxing_demo.sql`) | Row-level security / multi-tenant data access control, without a paid BI tier | `db/sandboxing_demo.sql`, [ADR-0024](adr/0024-metabase-as-code-and-oss-sandboxing.md) |
| A FastAPI service over the same Postgres data | A REST API layer for downstream consumers, with generated OpenAPI docs | `api/` |

Every item in that table is independently runnable locally with `docker compose up` and no
AWS account — see the [root README's Quickstart](../README.md#quickstart) and
[`CLAUDE.md`](../CLAUDE.md)'s "How to run the runnable parts."

## Skills demonstrated, with evidence

| Skill area | What's shown | Where |
|---|---|---|
| **Bioinformatics pipelines** | Nextflow DSL2, nf-core style, 12 modules, QC→align→call→validate | `pipeline/` |
| **Analytical validation** | `hap.py` vs GIAB truth; precision/recall/F1; explicit acceptance criterion | `pipeline/modules/validate/`, `docs/VALIDATION.md` |
| **Cloud / IaC** | AWS CDK (TypeScript), 6 stacks, Step Functions + Lambda orchestration, least-privilege IAM, CloudWatch | `infra/` |
| **Data engineering** | Insert-only Postgres schema, provenance + audit trail, migrations, star-schema warehouse (hand-rolled + dbt), Airflow-orchestrated refresh | `db/`, `dbt/`, `orchestration/` |
| **BI / reporting** | Two Metabase dashboards defined as version-controlled SQL, provisioned via REST API, row-level access control | `dashboards/` |
| **Machine learning** | **PyTorch** QLoRA fine-tuning of a small open LLM; model card; guardrails | `ai-report/`, `ai-report/MODEL_CARD.md` |
| **MLOps / responsible AI** | Human-in-the-loop, enforced guardrails in code, graceful degradation | [ADR-0008](adr/0008-guardrails-human-in-the-loop.md) |
| **DevOps** | Tiered CI/CD: Ruff lint, pip-audit + Trivy security, DB migration CI, pytest-cov + badge, Docker build/scan/GHCR, Dependabot, semver release, scheduled maintenance | `docker/`, `.github/workflows/`, [ADR-0016](adr/0016-cicd-strategy.md) |
| **Engineering judgement** | 28 Architecture Decision Records weighing trade-offs (including at least one recording a discarded first attempt) | `docs/adr/` |
| **Agentic AI** | ReAct-style tool-using agent: 5 LLM providers incl. Azure AI Foundry + AWS Bedrock, function-calling, ACMG classification, deterministic fallback, property-based testing | `ai-report/agent/`, [ADR-0014](adr/0014-agentic-variant-interpretation.md) |
| **AI integration engineering** | Same agent exposed 3 ways (CLI, REST + React, Streamlit) without duplicating logic; HL7 FHIR genomics intake; hybrid architecture (deterministic rule engine decides, LLM narrates) | `api/routers/agent.py`, `web/`, `ai-report/agent/fhir_intake.py`, [ADR-0027](adr/0027-rest-react-frontend-for-variant-interpreter.md), [ADR-0028](adr/0028-azure-bedrock-backends-and-fhir-intake.md) |
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

## The agentic AI component

The variant interpretation agent demonstrates **tool-using AI agents under clinical
safety constraints**:

- **ReAct loop** — the agent reasons step-by-step, calling tools (ClinVar, gnomAD, ACMG
  classifier) and observing results before producing a final classification.
- **Multi-provider LLM** — Ollama (local), OpenAI, Anthropic, **Azure AI Foundry**, and
  **AWS Bedrock** (via its model-agnostic Converse API), all with automatic fallback to a
  deterministic rule engine. See [ADR-0014](adr/0014-agentic-variant-interpretation.md) and
  [ADR-0028](adr/0028-azure-bedrock-backends-and-fhir-intake.md).
- **Three entry points, one agent** — a CLI, a REST API + React frontend
  ([ADR-0027](adr/0027-rest-react-frontend-for-variant-interpreter.md)), and a Streamlit demo
  all call the same `ReActAgent`/`DeterministicInterpreter` core rather than duplicating it.
- **HL7 FHIR intake** — `POST /agent/variant-review/fhir` accepts a (documented subset of a)
  FHIR genomics `Observation` alongside the manual-fields form, demonstrating an EMR-shaped
  integration point. See [ADR-0028](adr/0028-azure-bedrock-backends-and-fhir-intake.md).
- **Fully CI-smokable** — the deterministic backend proves the entire agent loop without
  real LLM inference; the cloud backends are unit-tested against mocked clients (no live
  cloud account needed). Property-based tests (Hypothesis, 200 examples/property) verify
  ACMG correctness invariants.
- **Safety by construction** — guardrails enforced in code: treatment language scrubbed,
  VUS flagged with uncertainty, mandatory review banner, evidence citations required.
- See the [Agent Model Card](../ai-report/agent/MODEL_CARD.md),
  [Design Doc](../ai-report/agent/DESIGN.md), and the [Variant Review UI](../web/README.md).

## What was actually run vs. what needs a full environment

Being straight about this (it's a portfolio, not a live service):

- **Verified running:** the metrics/provenance builder, the offline report renderer, the
  CPU LoRA fine-tuning smoke test, the unit-test suite, `dbt run`/`dbt test` against a
  seeded Postgres (CI), and the Airflow DAG end-to-end via `docker-compose.airflow.yml`
  (locally; the fixture-sync step alone is also CI-checked).
- **Needs Nextflow + Docker:** the full genomics pipeline on real GIAB data.
- **Needs an AWS account:** `cdk deploy` of the infrastructure (CI runs `cdk synth`).
- **Needs a GPU:** full QLoRA fine-tune of the 3B model (CPU smoke test proves the loop).

Status is tracked honestly in [docs/MILESTONES.md](MILESTONES.md).

## Resume bullets

Ready-to-paste lines, each backed by something in this repo — swap in whichever fit
the role:

- Built a solo, end-to-end clinical genomics platform (WGS reads → variant calling →
  GIAB truth-set validation → provenance-tracked Postgres → BI dashboard →
  QLoRA-fine-tuned LLM reporting) spanning Nextflow, AWS CDK, and PyTorch.
- Validated a germline SNV pipeline against the GIAB HG002 truth set with `hap.py`,
  meeting a precision/recall/F1 ≥ 0.99 acceptance threshold, with every result
  carrying a full provenance stamp (tool/reference versions, input checksums).
- Designed an insert-only Postgres schema with DB-level immutability triggers and a
  star-schema warehouse layer, enforcing an audit trail suitable for ISO 15189 /
  NATA-style accreditation patterns.
- Fine-tuned a small open LLM with QLoRA (PyTorch/PEFT/TRL) to draft plain-language
  variant reports, enforcing mandatory human-review guardrails and field citations
  in code rather than relying on model behavior.
- Wrote 24 Architecture Decision Records documenting trade-offs across bioinformatics,
  cloud infrastructure, data engineering, and responsible-AI design choices.
- Provisioned AWS infrastructure as code (CDK/TypeScript: S3, Lambda, Step Functions,
  least-privilege IAM) with automated guardrail tests enforcing accreditation-relevant
  invariants (versioning, TLS-only, deny-delete).

## Suggested reading order

1. [README](../README.md) — architecture + quickstart
2. This page
3. [Beginner's Guide](BEGINNERS-GUIDE.md) + [Glossary](GLOSSARY.md) — if the domain is new
4. [ADRs](adr/) — the engineering-judgement story
5. [Model Card](../ai-report/MODEL_CARD.md) + [VALIDATION](VALIDATION.md) — the rigor
