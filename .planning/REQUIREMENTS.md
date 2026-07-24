# Requirements: Clinical Genomics Insight Platform

**Defined:** 2026-07-21
**Core Value:** Every number the platform reports can be traced back to a provenance-stamped,
truth-set-validated run — and the repo never claims more than it has actually measured.
**Source:** `.planning/intel/` (36 classified docs, 16 ADRs) + `.planning/INGEST-CONFLICTS.md`

---

## Delivered baseline (not in current scope)

Milestones M0–M8 shipped these. They are **locked baseline**, not v1 scope — no phase in the
current roadmap re-plans them. Listed so requirement traceability stays complete and so future
milestones can see what already exists.

| ID | Requirement | Evidence |
|---|---|---|
| REQ-pipeline-execution | Nextflow DSL2 pipeline: fastp → FastQC → BWA-MEM2 → MarkDuplicates → caller → `hap.py` → export → MultiQC, with `QC_EVALUATE` after `HAPPY_BENCHMARK` | `pipeline/main.nf`, `pipeline/modules/`, `-stub` green in CI |
| REQ-serverless-orchestration | Step Functions + 7 Lambdas, ≤512 MB / ≤15 min, retry 2×/5 s/2.0, `maxConcurrency: 1` | `infra/lib/orchestration-stack.ts`, `lambdas/` |
| REQ-eventbridge-automation | S3 `raw/*.fastq.gz` → StartExecution; 14-day DLQ; DLQ-depth alarm | `infra/lib/orchestration-stack.ts` |
| REQ-s3-data-lake | Versioning, SSE-S3, TLS-only, BPA ×4, lifecycle, RETAIN | `infra/lib/data-lake-stack.ts`, `infra/test/stacks.test.ts` |
| REQ-dynamodb-metadata-store | Single table `cgp-metadata`, PK `run_id` / SK `record_type`, GSI, PAY_PER_REQUEST, PITR, RETAIN | `infra/lib/metadata-stack.ts` |
| REQ-observability | Structured JSON logs, SFN/Lambda alarms, 6 `CGP/QC` alarms → SNS | `infra/lib/observability-stack.ts` |
| REQ-iam-least-privilege | Per-Lambda roles; deny `dynamodb:DeleteItem`/`UpdateItem`/`DeleteTable`, `s3:DeleteObject` | `infra/lib/iam-stack.ts` |
| REQ-metabase-dashboard | Committed SQL cards over `v_run_summary` + 3 QC views, docker-compose | `dashboards/metabase/`, `db/schema.sql` |
| REQ-rag-reporting | Local FAISS retrieval + local LLM, guardrails, offline fallback | `ai-report/rag/`, `ai-report/infer.py` |
| REQ-lora-finetuning | QLoRA ≤3B, CPU smoke test <5 min, model card | `ai-report/train_lora.py`, `train_smoke.py`, `MODEL_CARD.md` |
| REQ-provenance-audit | Provenance stamp in `metrics.json`; audit actions; `ga4gh:SQ.` primitive | `pipeline/bin/build_metrics.py`, `ga4gh_ids.py` |
| REQ-docker-containerization | Per-step containers, digest pinning, pinned Lambda base image | `docker/`, module `container` directives |
| REQ-cicd | 9 GitHub Actions workflows | `.github/workflows/` |
| REQ-cost-guardrails | Zero Batch/Fargate/NAT/RDS/Bedrock/SageMaker asserted in synth; billing alarm | `infra/test/stacks.test.ts` |
| REQ-production-migration-docs | HealthOmics / Aurora / Bedrock / SageMaker + cost table | `docs/PRODUCTION-MIGRATION.md` |
| REQ-qc-warnings-self-healing | 6 metrics, adaptive mean±2σ, quarantine escalation, Choice-state routing, healer source | `pipeline/conf/qc_thresholds.yaml`, `lambdas/healer/` |
| REQ-variant-interpretation | ReAct agent, deterministic fallback, multi-provider LLM, chr20 SQLite KB | `ai-report/agent/` |
| REQ-validation-engine-xcmp | `hap.py` xcmp engine; docs consistent | `pipeline/modules/validate/happy_benchmark.nf`, `docs/VALIDATION.md` |
| REQ-cicd-tiers | Three-tier workflow architecture present | `.github/workflows/` |

**Known partial deliveries carried into v1 scope below:** REQ-cost-guardrails leaves an
unresolved compute-substrate gap (→ EXEC); REQ-qc-warnings-self-healing leaves the healer runtime
unplaced (→ EXEC-03); REQ-iam-least-privilege's deny test does not prove per-role attachment
(→ INTEG-01); REQ-cicd-tiers is not currently blocking (→ CI).

---

## v1 Requirements

Current milestone: **close the gap between what the repo claims and what it has proven.**

### Execution substrate (EXEC) — closes W1, W2

- [ ] **EXEC-01**: A new Accepted ADR records the authoritative answer to "where does real
      genomics compute run?", choosing explicitly between (a) cloud execution out of scope with
      local Nextflow documented as the sole real-compute path, (b) adopting AWS HealthOmics as a
      built path with the free-tier exception amended into the requirements, or (c) local
      Nextflow as sole real-compute path with cloud scoped to orchestration and metadata only.
- [ ] **EXEC-02**: No document in the repo states or implies that real genomics compute runs on
      AWS today in a way that contradicts EXEC-01 — specifically `docs/SOP-run-pipeline.md`,
      `docs/usage.md`, `docs/MILESTONES.md` M4, and the Consequences/Alternatives asides in
      ADR-0002 and ADR-0009 are corrected or annotated.
- [ ] **EXEC-03**: The healer Lambda's LLM runtime placement is stated in an ADR and matches the
      code and the CDK: either the rule-based fallback is declared the only cloud-deployed path,
      or an explicit endpoint contract and the healer's memory/timeout are recorded. A test
      asserts the deployed path never requires an in-Lambda Ollama server.

### Tamper-evidence integrity (INTEG) — closes W4

- [ ] **INTEG-01**: A CDK guardrail test asserts the `dynamodb:DeleteItem`, `dynamodb:UpdateItem`
      and `dynamodb:DeleteTable` deny statements are attached to **every** Lambda role that can
      write to `cgp-metadata` — not merely present somewhere in the synthesized template.
- [ ] **INTEG-02**: ADR-0012's compensating control #2 (DynamoDB Streams → append-only audit
      sink) is either built and asserted by a guardrail test, or recorded in an ADR as an
      accepted, named limitation with the residual risk stated.
- [ ] **INTEG-03**: Every tamper-evidence claim in the repo distinguishes the primary store's
      IAM-based, bypassable control from the replica's trigger-based, data-level control, so no
      document implies the primary store has unbypassable immutability.

### Machine-verified CI (CI)

- [ ] **CI-01**: `db-ci.yml` fails the job — non-zero exit, red status check — when schema apply,
      migration idempotency, seed load, or any immutability trigger test does not behave as
      expected. No result is swallowed by `|| true` or `|| echo`.
- [ ] **CI-02**: Every pull request produces 6 or more status checks, and the Tier 1 and Tier 2
      workflows named in ADR-0016 report pass/fail honestly rather than reporting green on
      internal failure.
- [ ] **CI-03**: The repo state matches ADR-0016 on blocking posture: either the non-blocking
      working-tree change is reverted, or it is committed alongside a new ADR that supersedes
      ADR-0016's blocking requirement and states why.

### Validation evidence (VAL) — closes W3

- [ ] **VAL-01**: A `hap.py` benchmark run over the **full chr20** is executed and
      `docs/VALIDATION.md` records the measured SNV precision, recall and F1 with the run's
      provenance stamp — no placeholders.
- [ ] **VAL-02**: A run at a representative clinical depth (~30–40×, downsampled from the 300×
      source BAM) is executed and recorded, so the reported metrics are not tied to an
      unrepresentative 255.8× depth.
- [ ] **VAL-03**: `docs/VALIDATION.md` states the validated region and depth explicitly and
      either matches ADR-0001's locked full-chr20 scope or cites a new ADR that narrows it, with
      the residual limitations (single sample, high-confidence BED exclusions, xcmp conservatism)
      still listed.

### Documentation accuracy (DOC)

- [ ] **DOC-01**: `CLAUDE.md` reflects reality — the correct ADR count, ADR-0012's supersession
      of insert-only Postgres as the primary store, and a non-negotiables list that no longer
      contradicts a locked ADR.
- [ ] **DOC-02**: `docs/adr/README.md` indexes every ADR file on disk, with correct status
      including all supersessions.
- [ ] **DOC-03**: `docs/ROADMAP.md`'s dangling reference to `docs/adr/0014-spatial-genomics-direction.md`
      is corrected — number 0014 is taken by the agentic variant interpretation ADR.

### Reviewer clickthrough (DEMO)

- [ ] **DEMO-01**: A reviewer starting from a single documented entry point can complete a
      three-minute clickthrough of the Streamlit demo — home → explorer → variant interpretation
      → assistant — with no database, no cloud account and no LLM.
- [ ] **DEMO-02**: The demo surfaces the measured validation numbers from VAL-01/VAL-02 on
      screen, alongside the scope-honesty statement, so a reviewer sees the evidence and its
      limits together.
- [ ] **DEMO-03**: Every demo page states on screen what is real measured output versus committed
      seed data or a deterministic stand-in.

## v2 Requirements

Acknowledged, deferred, not in the current roadmap.

### Standards

- **GA4GH-01**: Wire `ga4gh:SQ.<sha512t24u>` into run provenance alongside `reference_build`
  (ADR-0010's named next step, designed but not wired).
- **GA4GH-02**: Full VRS allele representation via the `ga4gh.vrs` library.

### Validation breadth

- **VALX-01**: Measured DeepVariant validation row alongside HaplotypeCaller.
- **VALX-02**: Cohort validation across more than one sample.

### Cloud

- **CLOUD-01**: If EXEC-01 chooses option (b), build the AWS HealthOmics private workflow path.
  Not committed until EXEC-01 resolves.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Clinical or diagnostic use | Portfolio artifact; not an accredited test. Scope honesty is a product requirement. |
| INDELs, SV, somatic calling, immune repertoire | ADR-0001 locks v1 to germline SNVs; INDEL reported for information only |
| Chromosomes other than chr20; whole-genome scale | ADR-0001 — keeps validation finishable by one person |
| AWS Batch, Fargate, NAT Gateway, RDS | REQ-cost-guardrails §14.3 forbids provisioning; guardrail tests assert zero |
| Bedrock, SageMaker endpoints, Comprehend, Rekognition, Kendra | Free-tier envelope; RAG and interpretation are local-only |
| Rebuilding anything from M0–M8 | Already delivered and tested; see PROJECT.md Current State |
| Team process artifacts (sprints, stakeholders, estimates) | One developer, one implementer |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| EXEC-01 | Phase 1 | Pending |
| EXEC-02 | Phase 1 | Pending |
| EXEC-03 | Phase 1 | Pending |
| INTEG-01 | Phase 2 | Pending |
| INTEG-02 | Phase 2 | Pending |
| INTEG-03 | Phase 2 | Pending |
| CI-01 | Phase 2 | Pending |
| CI-02 | Phase 2 | Pending |
| CI-03 | Phase 2 | Pending |
| VAL-01 | Phase 3 | Pending |
| VAL-02 | Phase 3 | Pending |
| VAL-03 | Phase 3 | Pending |
| DOC-01 | Phase 4 | Pending |
| DOC-02 | Phase 4 | Pending |
| DOC-03 | Phase 4 | Pending |
| DEMO-01 | Phase 5 | Pending |
| DEMO-02 | Phase 5 | Pending |
| DEMO-03 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0 ✓

---
*Requirements defined: 2026-07-21*
*Last updated: 2026-07-21 after documentation ingest and roadmap creation*
