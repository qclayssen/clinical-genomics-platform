# Clinical Genomics Insight Platform

## What This Is

An end-to-end **germline SNV** variant-calling platform built as a **portfolio project**: raw WGS
reads → QC → alignment → variant calling → benchmarked against the GIAB HG002 truth set with
`hap.py` → provenance-stamped results in a metadata store → Metabase ops dashboard → a QLoRA
fine-tuned LLM that drafts a plain-language summary behind enforced human-review guardrails,
plus an agentic ACMG/AMP variant interpreter and a Streamlit demo UI.

It demonstrates the validation and traceability **patterns** that ISO 15189 / NATA accreditation
ask for. It is **not an accredited clinical test** and must never be used for clinical decisions.
Scope honesty is a first-class product requirement, not a disclaimer.

The audience is a technical reviewer — a hiring manager, an interviewer, or a bioinformatics
engineer reading the repo cold.

## Core Value

Every number the platform reports can be traced back to a provenance-stamped, truth-set-validated
run — and the repo never claims more than it has actually measured.

## Current State

**This project is not greenfield.** Milestones M0–M8 (`docs/MILESTONES.md`) are built:

| Layer | State |
|---|---|
| Nextflow DSL2 pipeline (11+ modules, stub-runnable) | Built |
| Helper scripts + provenance stamp (`build_metrics.py`, `ga4gh_ids.py`) | Built, unit-tested |
| AWS CDK — 5 stacks + Jest guardrail tests | Built, `cdk synth` in CI |
| 7 Step Functions Lambdas + healer Lambda source | Built |
| Postgres schema (insert-only triggers) + demo seed | Built, triggers observed firing |
| Metabase dashboard definitions (committed SQL) | Built |
| AI reporting — offline renderer, fallback, QLoRA fine-tune, CPU smoke test | Built, offline path tested |
| Agentic variant interpreter (ReAct + deterministic fallback, chr20 SQLite KB) | Built |
| 16 ADRs, 9 CI workflows, ~281 passing tests | Built |
| Streamlit demo (`demo/`) — explorer, variant interpretation, assistant | Runnable locally |

The current milestone therefore does **not** re-build any of the above. It closes the gaps
between what the repo claims and what it has proven.

## Requirements

### Validated

Delivered by milestones M0–M8 and treated as locked baseline. Full list with evidence in
`.planning/REQUIREMENTS.md` → *Delivered baseline*.

- ✓ REQ-pipeline-execution — Nextflow DSL2 pipeline, stub-runnable, provenance-stamped — M0–M2
- ✓ REQ-serverless-orchestration — Step Functions + 7 Lambdas, ≤512 MB / ≤15 min — M4
- ✓ REQ-eventbridge-automation — S3 `raw/*.fastq.gz` → StartExecution, DLQ — M4
- ✓ REQ-s3-data-lake — versioned, encrypted, TLS-only, lifecycle, RETAIN — M4
- ✓ REQ-dynamodb-metadata-store — single-table `cgp-metadata`, PITR, RETAIN — M4
- ✓ REQ-observability — structured logs, SFN/Lambda/QC alarms → SNS — M4
- ✓ REQ-iam-least-privilege — per-Lambda roles, deny statements, guardrail tests — M4
- ✓ REQ-metabase-dashboard — committed SQL over `v_run_summary` — M6
- ✓ REQ-rag-reporting — local FAISS + local LLM + guardrails + offline fallback — M7
- ✓ REQ-lora-finetuning — QLoRA ≤3B, CPU smoke test, model card — M7
- ✓ REQ-provenance-audit — provenance stamp in `metrics.json`, audit actions — M2/M5
- ✓ REQ-docker-containerization — per-step containers, digest pinning — M3
- ✓ REQ-cicd — 9 GitHub Actions workflows across three tiers — M3
- ✓ REQ-cost-guardrails — zero Batch/Fargate/NAT/RDS asserted in synth — M4
- ✓ REQ-production-migration-docs — `docs/PRODUCTION-MIGRATION.md` — M8
- ✓ REQ-qc-warnings-self-healing — thresholds, adaptive σ, quarantine, Choice-state routing — post-M8
- ✓ REQ-variant-interpretation — ReAct agent + deterministic fallback, chr20 KB — post-M8
- ✓ REQ-validation-engine-xcmp — `hap.py` xcmp engine, docs consistent — post-M8
- ✓ REQ-cicd-tiers — three-tier workflow architecture in place — post-M8

### Active

Current milestone. Closes the four open ingest warnings plus documentation and demo integrity.
Full detail in `.planning/REQUIREMENTS.md`.

- [ ] **EXEC** — Record and enforce a single authoritative answer to "where does real genomics
      compute run?" (closes W1, W2)
- [ ] **INTEG** — Make the tamper-evidence claim true for the *primary* store, not only the
      demoted replica (closes W4)
- [ ] **CI** — Restore machine-verified, merge-blocking status checks as ADR-0016 requires
- [ ] **VAL** — Produce measured validation evidence over the full locked scope (closes W3)
- [ ] **DOC** — Bring `CLAUDE.md`, the ADR index and cross-references back in line with reality
- [ ] **DEMO** — Guarantee the three-minute reviewer clickthrough works and overclaims nothing

### Out of Scope

- **Clinical or diagnostic use of any kind** — this is a portfolio artifact; no phase may imply
  otherwise, and no output may drop the review banner.
- **INDELs, structural variants, somatic calling, immune repertoire** — ADR-0001 locks v1 to
  germline SNVs. INDEL numbers are reported for information only, never gated.
- **Chromosomes other than chr20; whole-genome scale** — ADR-0001.
- **AWS Batch, Fargate, NAT Gateways, RDS** — REQ-cost-guardrails §14.3 forbids provisioning
  them; CDK guardrail tests assert zero such resources.
- **Bedrock, SageMaker endpoints, Comprehend, Rekognition, Kendra, any paid cloud AI** —
  free-tier envelope; the RAG and interpretation paths are local-only.
- **AWS HealthOmics as a *built* path** — documented in `docs/PRODUCTION-MIGRATION.md` only.
  Building it is a candidate outcome of the EXEC decision, not a foregone one.
- **Re-planning or re-building M0–M8** — already delivered; see Current State.
- **Team process artifacts** — one developer, one implementer. No sprints, no stakeholders.

## Context

- **Runtime:** Python 3.11, Nextflow DSL2, Docker, AWS CDK (TypeScript), PostgreSQL, DynamoDB,
  Streamlit.
- **Primary success metric:** SNV F1 ≥ 0.99 vs the GIAB HG002 v4.2.1 truth set (ADR-0003),
  sustained across changes.
- **Secondary success metric:** a recruiter or hiring manager can complete a three-minute
  clickthrough of the demo (`docs/MILESTONES.md` M8).
- **Measured evidence today (2026-07-15):** HaplotypeCaller SNV precision 0.9934, recall 0.9894,
  F1 0.9914, INDEL F1 0.9971, Ti/Tv 2.07, mean depth 255.8×. Measured on
  `chr20:1,000,000-2,000,000` — a 1 Mb window, ~1/64th of the locked scope — at an
  unrepresentative depth. This is the gap the VAL requirements close.
- **Repo:** `github.com/qclayssen/clinical-genomics-platform`, branch
  `fix/chat-intent-routing-and-variant-page`.
- **Known drift:** `CLAUDE.md` claims 9 ADRs (there are 16) and presents insert-only Postgres as
  non-negotiable despite ADR-0012 superseding it. `docs/adr/README.md` indexes 12 of 16.
  `docs/SOP-run-pipeline.md`, `docs/usage.md` and `docs/MILESTONES.md` M4 still name AWS Batch as
  the cloud execution path. `docs/ROADMAP.md` reserves ADR number 0014, which is taken.
- **Uncommitted working tree:** a change making CI checks non-blocking (`|| echo "non-blocking"`
  wrappers in `db-ci.yml` and peers) is present but uncommitted. The developer has chosen to
  leave it for now. It directly contradicts ADR-0016's requirement that immutability and DB
  checks be machine-verified and blocking.

## Constraints

- **Scope**: GIAB HG002/NA24385, GRCh38 chr20, germline SNVs only — ADR-0001, so one person can
  actually finish and validate it.
- **Acceptance**: SNV F1 ≥ 0.99 in GIAB v4.2.1 high-confidence regions, computed by `hap.py`
  with the `xcmp` engine — ADR-0003 + ADR-0015. Any change to reference, caller or filtering
  re-triggers validation before tagging.
- **Cost**: AWS always-free tier. Lambda ≤ 512 MB / ≤ 15 min; Step Functions ≤ 4,000 transitions
  per month, `maxConcurrency: 1`; DynamoDB on-demand; `> $1` billing alarm. Tooling cost $0.
- **Compute**: Lambda cannot run BWA-MEM2, DeepVariant or `hap.py` on real WGS data — stated by
  ADR-0011 itself. Real compute currently runs locally via Nextflow.
- **Reproducibility**: every pipeline step in its own container pinned by immutable `@sha256:`
  digest — ADR-0009. Container identity lands in provenance.
- **Data integrity**: amend, never erase. Corrections are new records — ADR-0005 semantics
  carried forward by ADR-0012. Provenance fields are never removed.
- **AI safety**: all model output passes `enforce_guardrails()` — banner, provenance line, advice
  scrubbing, field citations — enforced in code, not prompts. ADR-0008 + ADR-0014.
- **Governance**: ADRs are append-only. Never rewrite one; supersede it and update its status.
- **Honesty**: never commit placeholder numbers to `docs/VALIDATION.md` as if measured.

## Key Decisions

<decisions status="LOCKED">
These 14 ADRs are Accepted and authoritative. They are **not to be re-litigated** during planning
or execution. Changing any of them requires a new, next-numbered ADR that supersedes it.

| ADR | Decision | Scope |
|---|---|---|
| ADR-0001 | Scope to GIAB HG002/NA24385, chr20, germline SNVs only | project scope |
| ADR-0002 | Nextflow DSL2, nf-core conventions, one process per module file | pipeline framework |
| ADR-0003 | Truth-set benchmarking is a first-class stage; **SNV F1 ≥ 0.99** acceptance criterion (engine choice only superseded by ADR-0015) | validation |
| ADR-0006 | Metabase ops dashboard from committed SQL over `v_run_summary` | BI |
| ADR-0007 | QLoRA fine-tune of a ≤3B open model, CPU smoke test + offline fallback mandatory | ML |
| ADR-0008 | `enforce_guardrails()` in code; human-in-the-loop sign-off; model sees metrics only | AI safety |
| ADR-0009 | Per-step containers pinned by immutable sha256 digest; tag pinning rejected | reproducibility |
| ADR-0010 | Incremental GA4GH alignment; `sha512t24u` implemented, rest documented honestly | standards |
| ADR-0011 | Serverless compute: Step Functions + 7 Lambdas + EventBridge, free-tier, $0 idle | cloud compute |
| ADR-0012 | DynamoDB primary metadata store; Postgres demoted to Metabase read-replica | datastore |
| ADR-0013 | QC warnings, adaptive mean±2σ thresholds, multi-level self-healing, notify-then-auto-execute | QC/remediation |
| ADR-0014 | Agentic ACMG/AMP variant interpretation via ReAct loop with deterministic fallback | AI interpretation |
| ADR-0015 | `hap.py` **xcmp** engine, not vcfeval | validation engine |
| ADR-0016 | Three-tier CI/CD; DB migration + immutability tests machine-verified and **blocking**; 6+ status checks per PR | CI/CD |
</decisions>

<decisions status="SUPERSEDED">
Retained for provenance. Not authoritative for the superseded portion.

| ADR | Superseded by | What survives |
|---|---|---|
| ADR-0004 (Batch/Fargate compute) | ADR-0011, **compute only** | CDK/IaC, S3 data lake, scoped IAM, Jest guardrail tests remain authoritative |
| ADR-0005 (insert-only Postgres as primary) | ADR-0012 | "amend, never erase" semantic survives; the trigger-level immutability guarantee does **not** survive for the primary store |
</decisions>

### Open decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Where does real genomics compute run in the cloud? | ADR-0011 states Lambda cannot run BWA-MEM2/DeepVariant/`hap.py`; REQ-cost-guardrails forbids Batch/Fargate/NAT/RDS. There is currently **no** stated cloud execution substrate. Options: (a) declare cloud execution out of scope and document local Nextflow as the sole real-compute path; (b) supersede with an ADR adopting AWS HealthOmics, amending §14.3/§14.5; (c) keep local Nextflow as the sole real-compute path and scope cloud work to orchestration and metadata only. | — Pending (Phase 1) |
| Where does the healer Lambda's Ollama runtime execute? | ADR-0013 specifies an Ollama-based healer but is silent on memory and placement; `lambdas/healer/handler.py` calls `http://localhost:11434`, which does not exist inside a 512 MB Lambda. The rule-based fallback may be the only cloud-deployed path. | — Pending (Phase 1) |
| Is DynamoDB's IAM-based append-only control sufficient, or does it need a Streams audit sink? | ADR-0012 names the Streams → append-only sink as compensating control #2 but it is not built, and no guardrail test asserts it. | — Pending (Phase 2) |
| Does the locked scope stay full chr20, or narrow to the measured window? | ADR-0001 outranks `docs/VALIDATION.md`, so the scope stays chr20 and the *evidence* is what is incomplete. Narrowing would require a new ADR. | — Pending (Phase 3) |

---
*Last updated: 2026-07-21 after documentation ingest (`gsd-ingest-docs`) over 36 classified documents*
