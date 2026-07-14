# Build milestones — demoable at every stage

Pipeline first, then containers/CI, then infra, then DB, then dashboard, then AI.
Each milestone produces something you can screen-share, not just code that compiles.

| # | Build | Demoable artifact |
|---|---|---|
| **M0** | Repo scaffold; stage GIAB HG002 chr20 inputs | `nextflow run -profile test -stub` prints the execution DAG |
| **M1** | Core pipeline local: QC → align → mark-dup → HaplotypeCaller | A real chr20 VCF + MultiQC HTML report |
| **M2** | Validation: `hap.py` vs GIAB truth; provenance stamp into `metrics.json` | One-page validation summary: precision / recall / F1 |
| **M3** | Per-stage pinned Dockerfiles; GitHub Actions (lint + stub + tests) | Green CI badge; PR auto-runs the test profile |
| **M4** | CDK: S3 data lake, Batch, scoped IAM, CloudWatch | `cdk deploy`, then the same pipeline runs on AWS Batch unmodified |
| **M5** | Postgres schema + ingestion step | SQL query joining a sample → run → tool versions → QC metrics |
| **M6** | Metabase on the same Postgres | Live dashboard: QC trends, turnaround, pass/fail |
| **M7** | QLoRA fine-tune; mandatory review flag on every report | Structured JSON beside its generated summary, with field citations |
| **M8** | README + VALIDATION + demo GIF + resume bullets | Three-minute clickthrough for a hiring manager |

## Current status

| Layer | State |
|---|---|
| Pipeline (Nextflow DSL2, 11 modules) | ✅ scaffolded, stub-runnable |
| Helper scripts + provenance | ✅ implemented, unit-tested |
| AWS CDK (4 stacks + guardrail tests) | ✅ scaffolded |
| Postgres schema (insert-only + triggers) | ✅ implemented, demo seed |
| Metabase dashboard definitions | ✅ documented + SQL provided |
| AI reporting (offline + fine-tune paths) | ✅ implemented, offline path tested |
| CI (pipeline + infra) | ✅ workflows in place |

> "Scaffolded" = structure and logic are in place and the dependency-free parts run
> and are tested. Running the full pipeline end-to-end needs Nextflow + Docker + the
> staged GIAB data on your machine; deploying infra needs an AWS account.
