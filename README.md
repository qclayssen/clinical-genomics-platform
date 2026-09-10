<!-- markdownlint-disable MD041 MD033 — custom badges and HTML layout require these exceptions.
     project: clinical-genomics-platform; author: Quentin Clayssen; scope: solo-built;
     stack: Nextflow DSL2, AWS CDK, DynamoDB + Postgres, Metabase, PyTorch QLoRA;
     validation: hap.py vs GIAB HG002 truth set, SNV F1=0.9914, ISO 15189 patterns;
     architecture: 29 ADRs, hand-written nf-core-style modules, not scaffolded from template.

     No coverage badge here on purpose: publishing one needs a gist plus a GIST_TOKEN
     secret and a COVERAGE_GIST_ID variable (see .github/workflows/coverage.yml). Until
     those exist the badge URL 404s, and a broken badge reads worse than none. Coverage
     is reported in the PR comment and the pipeline-ci log instead. -->

<div align="center">

# Clinical Genomics Insight Platform

**An end-to-end germline variant-calling platform built for production-grade clinical bioinformatics**

From raw WGS reads to validated variants, structured provenance, ops dashboards, and AI-drafted reports.

<br/>

**Built by [Quentin Clayssen](https://github.com/qclayssen)** · Solo-designed, solo-built, AI-orchestrated

<br/>

[![CI — Pipeline](https://img.shields.io/github/actions/workflow/status/qclayssen/clinical-genomics-platform/pipeline-ci.yml?label=Pipeline%20CI&style=flat-square&logo=githubactions&logoColor=white)](https://github.com/qclayssen/clinical-genomics-platform/actions/workflows/pipeline-ci.yml)
[![CI — Infra](https://img.shields.io/github/actions/workflow/status/qclayssen/clinical-genomics-platform/infra-ci.yml?label=Infra%20CI&style=flat-square&logo=githubactions&logoColor=white)](https://github.com/qclayssen/clinical-genomics-platform/actions/workflows/infra-ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)
[![Nextflow DSL2](https://img.shields.io/badge/Nextflow-DSL2-23b45e?style=flat-square&logo=nextflow&logoColor=white)](https://www.nextflow.io/)
[![AWS CDK](https://img.shields.io/badge/AWS-CDK-FF9900?style=flat-square&logo=amazonaws&logoColor=white)](https://aws.amazon.com/cdk/)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)

</div>

<br/>

<div align="center">
  <sub>Built to demonstrate the stack that clinical-bioinformatics and AWS-genomics roles screen for — scoped so a single person can finish it.</sub>
</div>

<br/>

<p align="center">
  <a href="#architecture">Architecture</a> ·
  <a href="#validation-summary">Validation</a> ·
  <a href="#quickstart">Quickstart</a> ·
  <a href="#capability-walkthrough">Walkthrough</a> ·
  <a href="#documentation">Docs</a> ·
  <a href="docs/FOR-RECRUITERS.md">For Recruiters</a>
</p>

<br/>

<div align="center">
  <img src="docs/media/demo.gif" alt="Clinical Genomics Insight Platform — Streamlit demo walkthrough: Home, Data Explorer, Variant Interpretation, Pipeline Assistant" width="800"/>
</div>

<div align="center">
  <sub>The Streamlit demo (<code>demo/</code>) — no database, cloud account, or LLM required. See <a href="demo/README.md">demo/README.md</a>.</sub>
</div>

<br/>

---

<br/>

## Overview

This platform implements the full path from sequencing data to clinical insight:

**QC** | **Alignment** | **Variant Calling** | **Truth-Set Benchmarking** | **Postgres Provenance** | **Metabase Dashboards** | **LLM Report Drafting**

<br/>

> **Nextflow style, not the nf-core template.** The pipeline follows nf-core conventions
> (DSL2, one process per module, `conf/modules.config`, per-process `versions.yml`, module
> `meta.yml`) but is hand-written — it does not include the template's `subworkflows/nf-core/utils_*`
> backbone, nf-schema validation, or nf-test suite, and would not pass `nf-core lint` cleanly.

> **Scope honesty.** This is a portfolio project. It demonstrates the validation methodology
> and traceability patterns ISO 15189 / NATA accreditation requires (benchmarking against a
> reference truth set, insert-only provenance, audit trails, change control). It is not an
> accredited clinical test and must not be used for clinical decision-making.

<br/>

---

<br/>

## Architecture

> Lambda functions handle orchestration and metadata; heavy bioinformatics compute
> (alignment, variant calling) runs via Nextflow + Docker locally or on compute instances.

```mermaid
flowchart TD
    subgraph Local["Local / Compute"]
        NF["Nextflow DSL2 pipeline<br/>(QC → align → call → validate → export)"]
    end

    subgraph AWS["AWS (CDK-managed)"]
        S3["S3 Data Lake<br/>raw/ • aligned/ • called/ • validated/"]
        EB["EventBridge"]
        SF["Step Functions<br/>state machine"]

        subgraph Lambdas["Lambda Functions (orchestration)"]
            L1["ingestion_trigger"]
            L2["qc_orchestrator"]
            L3["variant_calling"]
            L4["validation_checker"]
            L5["export_handler"]
            L6["metadata_ingestor"]
            L7["report_generator"]
        end

        HEAL["healer<br/>(self-healing / retry)"]
        DDB["DynamoDB<br/>(primary metadata store)"]
        PG["Postgres<br/>(Metabase read-replica)"]
        MB["Metabase Dashboard<br/>(QC trends, turnaround, pass/fail)"]
        CW["CloudWatch + SNS<br/>(alarms & notifications)"]
    end

    subgraph AI["AI Report Layer"]
        QLORA["QLoRA-tuned LLM<br/>structured JSON → draft summary"]
        AGENT["ReAct Agent<br/>VCF → ClinVar/gnomAD/ACMG<br/>variant interpretation"]
    end

    NF -- "FASTQ / VCF / metrics.json<br/>(provenance-stamped)" --> S3
    S3 -- "object created" --> EB
    EB --> SF
    SF --> L1 --> L2 --> L3 --> L4 --> L5 --> L6 --> L7
    SF -.-> HEAL
    L6 --> DDB
    DDB -- "sync" --> PG
    PG --> MB
    L7 --> QLORA --> AGENT
    SF --> CW
```

<br/>

---

<br/>

## Validation Summary

The pipeline is benchmarked on **GIAB HG002 / NA24385, chromosome 20** (1 Mb window,
chr20:1,000,000-2,000,000, 300x depth) against the v4.2.1 high-confidence truth set
using `hap.py`. Full methodology in [`docs/VALIDATION.md`](docs/VALIDATION.md).

<br/>

<div align="center">

| Metric | GATK HaplotypeCaller | DeepVariant | Source |
|:---|:---:|:---:|:---|
| SNV Precision | 0.9934 | — | `hap.py` summary.csv |
| SNV Recall | 0.9894 | — | `hap.py` summary.csv |
| **SNV F1** | **0.9914** | — | `hap.py` summary.csv |
| INDEL F1 | 0.9971 | — | `hap.py` summary.csv |
| Ti/Tv | 2.07 | — | `bcftools stats` |

</div>

<br/>

SNV F1 meets the >= 0.99 acceptance criterion. DeepVariant comparison is planned.

<br/>

---

<br/>

## Quickstart

```bash
# 1. Stage the tiny test data (subset, ships in-repo) and run the stub DAG
cd pipeline
nextflow run main.nf -profile test,docker -stub

# 2. Full local run on GIAB HG002 chr20.
#    Nothing is downloaded automatically: `-profile test` points at the tiny
#    committed placeholders, so stage the real data first (~10 GB).
./scripts/fetch_testdata.sh && ./scripts/preflight.sh
nextflow run main.nf -profile test,docker \
  --reference <staged.fa> --truth_vcf <staged.vcf.gz> --truth_bed <staged.bed>

# 3. Deploy the AWS storage/metadata layer. Compute stays local by design —
#    `-profile aws` provisions no cloud executor, it publishes results to the
#    S3 data lake and turns on metadata ingest (ADR-0017, ADR-0018).
cd ../infra && npm ci && npx cdk synth && npx cdk deploy --all
cd ../pipeline
export CGP_S3_BUCKET=... CGP_DB_URL=...
nextflow run main.nf -profile docker,aws
```

See [`docs/SOP-run-pipeline.md`](docs/SOP-run-pipeline.md) for the full operating procedure and acceptance criteria.

<br/>

---

<br/>

## Repository Layout

```
clinical-genomics-platform/
│
├── pipeline/               Nextflow DSL2 modules: QC → align → call → validate → export
├── infra/                  AWS CDK app: S3 data lake, DynamoDB metadata, Step Functions +
│                           Lambda orchestration, scoped IAM, CloudWatch (6 stacks)
├── lambdas/                Handlers for the serverless path: ingestion, metadata, QC
│                           orchestration, validation, reporting, export, LLM healer
├── db/                     Postgres schema + migrations (samples, runs, QC, provenance, audit)
├── dashboards/metabase/    Version-controlled dashboard + question definitions
├── dbt/                    dbt analytics layer rebuilding the star schema (ADR-0025)
├── orchestration/          Airflow DAG for the warehouse ETL (ADR-0023, ADR-0026)
├── api/                    FastAPI REST service + OpenAPI docs over runs/QC/provenance
├── web/                    React + Vite UI for agentic variant review and sign-off
├── demo/                   Streamlit walkthrough over the committed fixtures
├── emr-pipeline/           Separate ICU/VVED demo: mock EMR → insert-only warehouse →
│                           LLM-structured consult notes → stub ANZICS-APD export (ADR-0029)
├── ai-report/              PyTorch QLoRA fine-tune + inference for AI-drafted summaries
├── ai-report/agent/        ReAct variant interpretation agent (ACMG classification)
├── docker/                 Dockerfile.tools (helper scripts) + Dockerfile.demo; per-stage
│                           tool containers are pinned in each module's `container` directive
├── scripts/                fetch_testdata.sh, preflight.sh, and other helpers
├── docs/                   Validation report, SOP, beginner's guide, glossary, ADRs
├── tests/                  Unit tests + small committed fixtures
└── .github/workflows/      CI/CD: lint, security, DB validation, coverage, Docker, release, maintenance
```

<br/>

---

<br/>

## Documentation

<div align="center">

| Audience | Resource |
|:---|:---|
| New to the domain | [Beginner's Guide](docs/BEGINNERS-GUIDE.md) and [Glossary](docs/GLOSSARY.md) |
| Recruiter / Hiring manager | [For Recruiters](docs/FOR-RECRUITERS.md) |
| Technical decisions | [Architecture Decision Records](docs/adr/) |
| Accuracy and benchmarking | [Validation Report](docs/VALIDATION.md) |
| ML component | [Model Card](ai-report/MODEL_CARD.md) and [ADR-0007](docs/adr/0007-qlora-small-open-model.md) |
| Agentic AI | [Agent Design](ai-report/agent/DESIGN.md) and [Agent Model Card](ai-report/agent/MODEL_CARD.md) |
| Operations | [SOP](docs/SOP-run-pipeline.md) and [Runbook](docs/RUNBOOK.md) |
| Standards interoperability | [GA4GH Alignment](docs/GA4GH-ALIGNMENT.md) |

</div>

<br/>

---

<br/>

## Milestones

The build is demoable at every stage — see [`docs/MILESTONES.md`](docs/MILESTONES.md) for the full timeline.

<br/>

---

<br/>

## Dashboard Preview

<p align="center">
  <sub>QC trends, turnaround time, and validation pass/fail — powered by Metabase over Postgres, provisioned entirely as code (<code>dashboards/metabase/dashboard_manifest.yaml</code> + <code>provision_metabase.py</code>).</sub>
</p>

<p align="center">
  <img src="docs/assets/metabase-dashboard-demo.gif" alt="Animated walkthrough of both Metabase dashboards" width="720"/>
</p>

<p align="center">
  <sub>Both dashboards, scrolled through live — not a mockup.</sub>
</p>

<p align="center">
  <img src="docs/assets/metabase-clinical-genomics-ops.png" alt="Clinical Genomics Ops dashboard — validation pass rate, turnaround time, runs per week" width="720"/>
</p>

<p align="center">
  <sub><b>Clinical Genomics Ops</b> — the daily-standup view: validation pass rate, per-run turnaround, runs/week throughput.</sub>
</p>

<p align="center">
  <img src="docs/assets/metabase-clinical-genomics-analytics.png" alt="Clinical Genomics Analytics dashboard — SNV F1 trend, duplication rate, turnaround SLA, self-service cohort explorer" width="720"/>
</p>

<p align="center">
  <sub><b>Clinical Genomics Analytics</b> — the star-schema warehouse layer: SNV F1 trend by pipeline version, turnaround SLA p50/p95, a self-service cohort explorer.</sub>
</p>

> Reproduce it yourself: `docker compose up -d`, complete Metabase's one-time setup at
> `localhost:3000`, then `MB_USERNAME=... MB_PASSWORD=... python dashboards/metabase/provision_metabase.py`
> — see [`dashboards/metabase/README.md`](dashboards/metabase/README.md).

<br/>

---

<br/>

## Capability Walkthrough

<p align="center">
  <sub>Every screenshot below is a real capture of the actual running service — no mockups.</sub>
</p>

### REST API — OpenAPI docs

<p align="center">
  <img src="docs/assets/api-openapi-docs.png" alt="FastAPI OpenAPI docs — runs, provenance, QC-warnings, agent variant-review endpoints" width="720"/>
</p>

<p align="center">
  <sub>`uvicorn api.main:app --reload` — fixture-backed by default, generated OpenAPI 3.1 spec, no database required.</sub>
</p>

### Streamlit demo app — data explorer and agentic variant interpretation

<p align="center">
  <img src="docs/assets/demo-app-home.png" alt="Streamlit demo app home page" width="720"/>
</p>

<p align="center">
  <img src="docs/assets/demo-app-explorer.png" alt="Streamlit Pipeline Data Explorer — KPIs, filters, SNP F1 accuracy trend" width="720"/>
</p>

<p align="center">
  <img src="docs/assets/demo-app-interpret.png" alt="Streamlit Variant Interpretation page — agent reasoning trace, ACMG classification" width="720"/>
</p>

<p align="center">
  <sub><code>PYTHONPATH=. streamlit run demo/app.py</code> — reads committed seed data and fixtures, no database or cloud account needed. See <a href="demo/README.md">demo/README.md</a>.</sub>
</p>

### Agentic variant-review UI (React + FastAPI)

<p align="center">
  <img src="docs/assets/variant-review-form.png" alt="Variant Review UI — submit a variant for agentic ACMG classification" width="720"/>
</p>

<p align="center">
  <img src="docs/assets/variant-review-trace.png" alt="Variant Review UI — full agent tool-call trace, ACMG classification, provenance, clinician sign-off" width="720"/>
</p>

<p align="center">
  <sub>A clinician submits a variant, watches the agent call ClinVar/gnomAD/ACMG tools step by step, and records sign-off through the insert-only <code>review-decisions</code> endpoint. See <a href="web/README.md">web/README.md</a> and <a href="docs/adr/0027-rest-react-frontend-for-variant-interpreter.md">ADR-0027</a>.</sub>
</p>

### dbt lineage graph

<p align="center">
  <img src="docs/assets/dbt-lineage-graph.png" alt="dbt lineage graph — sources through staging views to star-schema marts" width="600"/>
</p>

<p align="center">
  <sub>Source tables → staged views → dimension/fact marts, auto-generated by <code>dbt docs generate</code>. See <a href="dbt/README.md">dbt/README.md</a> and <a href="docs/adr/0025-dbt-analytics-engineering-layer.md">ADR-0025</a>.</sub>
</p>

<br/>

---

<br/>

## Contributing

This is a solo portfolio project. Issues, questions, and feedback are welcome — open an
issue or start a discussion. Unsolicited pull requests are unlikely to be merged, but feel
free to fork.

<br/>

## License

MIT — see [`LICENSE`](LICENSE). Reference data (GIAB) is public domain / CC0 from NIST.
