# Constraints (SPEC intel)

Extracted from the three SPEC-classified documents in `.kiro/specs/clinical-genomics-platform/`.
Precedence note: SPEC ranks below ADR. Where a locked ADR contradicts a constraint below, the
ADR wins and the override is stated inline and logged in `INGEST-CONFLICTS.md`.

---

## C-arch-cdk-stacks — CDK stack decomposition
- source: `.kiro/specs/clinical-genomics-platform/design.md` §CDK Stack Restructuring
- type: architecture
- constraint: five stacks, wired in `infra/bin/app.ts` —
  - `data-lake-stack.ts` — EVOLVED (S3 data lake, retained from ADR-0004)
  - `orchestration-stack.ts` — NEW, replaces `compute-stack` (Step Functions + EventBridge)
  - `metadata-stack.ts` — NEW (DynamoDB single table)
  - `iam-stack.ts` — REPLACED (per-Lambda least-privilege roles)
  - `observability-stack.ts` — EVOLVED (Lambda/SFN metrics and alarms)
- rationale: each component migrates to its production counterpart independently; the modular
  stack split ensures no coupling between migration phases (`docs/PRODUCTION-MIGRATION.md`).

## C-data-dynamodb-single-table — DynamoDB single-table design
- source: `design.md` §Data Models / DynamoDB Single-Table Design; `requirements.md` §5
- type: schema
- constraint: PK `run_id` (String), SK `record_type` (String); GSI
  `sample_id-created_at-index` (PK `sample_id`, SK `created_at`); `PAY_PER_REQUEST` billing;
  PITR enabled; removal policy RETAIN; every item carries `created_at` as ISO 8601 UTC with
  seconds precision.
- record_type enum: `RUN`, `QC_METRICS`, `PROVENANCE`, `AUDIT`, `CORRECTION`
  — **extended by ADR-0013 (LOCKED) to include `QC_WARNING`.**
- append-only mechanism: IAM deny of `dynamodb:DeleteItem` / `dynamodb:UpdateItem` /
  `dynamodb:DeleteTable` on every Lambda role. Corrections are new `CORRECTION` items carrying
  `original_record_type` and `correction_reason`.

## C-data-s3-prefixes — S3 data lake prefix structure and lifecycle
- source: `design.md` §S3 Data Lake Prefix Structure; `requirements.md` §4
- type: schema
- constraint: prefixes `raw/`, `work/`, `results/`. `work/` current versions expire at 14 days;
  `raw/` transitions to Infrequent Access at 30 days and Glacier at 180 days. Versioning on,
  SSE-S3 default encryption, all four Block Public Access settings on, bucket policy Deny on
  `aws:SecureTransport = false`, removal policy RETAIN.
- IAM: explicit deny on `s3:DeleteObject` and `s3:DeleteObjectVersion` for `raw/*` and
  `results/*` with no exception for any role.

## C-data-provenance-stamp — Provenance stamp schema
- source: `design.md` §Provenance Stamp Schema (within metrics.json); `requirements.md` §11
- type: schema
- constraint: a JSON object embedded in `metrics.json` containing git commit SHA (40-char
  hex), pipeline version (semver), caller tool name and version, reference genome build
  identifier and version, truth set version, and SHA-256 checksums of all input FASTQ files.
- ADR overlay: ADR-0009 (LOCKED) additionally requires container identity in the provenance
  record. ADR-0010 (LOCKED) names the `ga4gh:SQ.<sha512t24u>` reference identifier as the
  chosen next addition, alongside `reference_build` — designed, not yet wired.
- immutability rule (from CLAUDE.md and ADR-0005/0012): fields are never removed from the
  provenance stamp.

## C-nfr-freetier — AWS always-free-tier envelope
- source: `requirements.md` §14; `design.md` §AWS Free-Tier Cost Model; ADR-0011
- type: nfr
- constraint:
  - Lambda: memory <= 512 MB, timeout <= 15 min (free tier 1M requests + 400k GB-s/month)
  - Step Functions: <= 4,000 state transitions/month; state machine `maxConcurrency: 1`
  - DynamoDB: on-demand, 25 GB storage
  - **Prohibited resource types:** `AWS::Batch::*`, `AWS::ECS::Service`,
    `AWS::EC2::NatGateway`, `AWS::RDS::*`, `AWS::Bedrock::*`, `AWS::SageMaker::Endpoint`,
    `AWS::Kendra::*`, `AWS::Comprehend::*` — asserted zero by CDK guardrail tests
  - Billing alarm on `AWS/Billing` `EstimatedCharges` > $1 USD, single 6-hour period, SNS
- consequence: this constraint plus ADR-0011's stated Lambda limitation is the source of the
  cloud-execution-substrate gap (WARNING W1).

## C-nfr-retry-semantics — Retry and error handling
- source: `design.md` §Error Handling; `requirements.md` §1.6, §2.4, §5.9
- type: nfr
- constraint:
  - Pipeline retryable exit codes: 137, 143, 104, 134, 139 — retry up to 2 times, then emit a
    structured error with process name, exit code and stderr.
  - Step Functions Lambda retry: 2 attempts, 5s initial interval, backoff rate 2.0.
  - DynamoDB writes: up to 3 retries with exponential backoff; on exhaustion publish a
    CloudWatch alarm and fail the execution without discarding pending audit data.
  - RAG reporter: local LLM failing within 120 seconds or raising any runtime error falls back
    to the deterministic offline renderer with a logged warning.
- ADR overlay: ADR-0013 (LOCKED) layers pattern-based Choice-state routing and a max-2
  self-healing attempt cap on top of these numeric retries.

## C-protocol-eventbridge — S3 event key matching
- source: `requirements.md` §3; `design.md` §Correctness Property 4
- type: protocol
- constraint: match objects under `raw/` including nested sub-prefixes, extensions
  `.fastq.gz` or `.fq.gz`, case-insensitive. Non-matching extensions must not trigger.
  Versioned re-uploads of an existing key DO trigger a new execution (no deduplication).
  Execution start within 60 seconds of object creation. Rule retry 3 attempts with exponential
  backoff; DLQ retention 14 days; alarm on DLQ depth >= 1.
  Input payload: bucket name, object key, object size.

## C-protocol-audit-records — Audit record construction
- source: `design.md` §Correctness Properties 7-9; `requirements.md` §2.3, §2.5, §11
- type: protocol
- constraint: defined actions and required fields —
  - `WORKFLOW_COMPLETE` — run_id, execution start, execution end, ISO 8601 completion timestamp
  - `WORKFLOW_FAILED` — run_id, failed state name, error cause, ISO 8601 timestamp
  - `PIPELINE_COMPLETE` — run_id, ISO 8601 UTC timestamp, written within 30 seconds
  - `REPORT_DRAFTED` — run_id, model version, adapter version (or `null` for zero-shot), timestamp
  - `VALIDATION_FAILED` — run_id, observed F1, written when SNV F1 < 0.99
  - `CORRECTION` items preserve the original record unchanged.

## C-contract-guardrails — AI output contract
- source: `requirements.md` §9.6; `design.md` §Correctness Property 10; ADR-0008 (LOCKED)
- type: api-contract
- constraint: every AI-generated report must pass `enforce_guardrails()`, which guarantees:
  the `AI-DRAFTED — REQUIRES CLINICIAN REVIEW` banner (re-inserted if absent), a provenance
  citation line, scrubbing of clinical-recommendation phrasing (`recommend`, `diagnose`,
  `treat with`) to `[review required]`, and field-level citations. The model receives only
  structured metrics — never raw reads, never the VCF body. Output length 120-300 words.
  The step cannot be skipped; a human signs off before the banner is removed.
- ADR-0014 (LOCKED) extends the same code-enforced-not-prompt-enforced pattern to variant
  interpretation: no treatment language, mandatory VUS uncertainty flags, review banner,
  required evidence citations.

## C-contract-rag-retrieval — RAG retrieval constraints
- source: `requirements.md` §9.1-9.5; `design.md` §Correctness Property 11
- type: api-contract
- constraint: local vector store (FAISS or ChromaDB); at most 5 retrieved passages; each
  passage <= 512 tokens; cosine similarity threshold >= 0.70; fewer than 5 (including zero)
  qualifying passages must not error. Generation runs on local compute only — no Bedrock, no
  paid SageMaker endpoints.

## C-nfr-containers — Container pinning
- source: `requirements.md` §12; ADR-0009 (LOCKED)
- type: nfr
- constraint (ADR-0009 authoritative): every pipeline step runs in its own container,
  Biocontainers where available, **pinned by immutable sha256 digest in production**. Tag
  pinning is explicitly rejected for pipeline images. Lambda container images build from a
  version-controlled Dockerfile with a digest-pinned base. Every dependency install step pins
  exact versions.
- SPEC deviation (overridden): `requirements.md` §12.1 permits "exact version tag for images
  from registries that do not publish digests". ADR-0009 outranks this; the exemption is
  narrowed to registries that genuinely cannot supply a digest. §12.4 (Metabase pinned to an
  exact release tag) stands — Metabase is not a pipeline step.

## C-nfr-testing — Testing strategy
- source: `design.md` §Testing Strategy; `requirements.md` §13
- type: nfr
- constraint: dual approach —
  - Property-based tests (Hypothesis, Python) covering 13 named correctness properties:
    provenance round-trip, validation outcome determination, exit code classification,
    EventBridge key matching, DynamoDB record type validation, ISO 8601 formatting, audit
    record construction (completion and failure), correction record integrity, guardrails
    enforcement, RAG retrieval constraints, report word-count bounds, model card completeness.
  - CDK guardrail tests (Jest, TypeScript) asserting infrastructure invariants including zero
    prohibited resource types and no `*`/`iam:*` in Lambda role policies.
  - Unit tests (pytest) and integration tests.
- ADR-0013 (LOCKED) claims 212 Python tests + 66 CDK tests for the QC/self-healing layer.

## C-nfr-ci-permissions — CI workflow permissions
- source: `requirements.md` §13.7 (SPEC) vs ADR-0016 (LOCKED, precedence 0)
- type: nfr
- constraint (ADR-0016 authoritative): workflows request the least privilege each tier needs,
  which is more than `contents: read` for several workflows — `issues: write` for
  `maintenance.yml`, security-events write for SARIF upload, packages write for GHCR push,
  pull-requests write for coverage comments, contents write for releases.
- SPEC deviation (overridden): `requirements.md` §13.7 requires `contents: read` for **all**
  workflow jobs. ADR-0016 postdates and outranks it. Recorded as auto-resolved INFO.

## C-nfr-caller-selection — Variant caller
- source: `requirements.md` §1.8; `docs/VALIDATION.md`
- type: nfr
- constraint: caller selectable between GATK HaplotypeCaller and DeepVariant via a parameter,
  defaulting to HaplotypeCaller. Only HaplotypeCaller has a measured validation row to date.

## C-nfr-validation-acceptance — Analytical acceptance criterion
- source: ADR-0003 (LOCKED), ADR-0015 (LOCKED), `docs/VALIDATION.md`, `requirements.md` §1.3
- type: nfr
- constraint: **SNV F1 >= 0.99** within GIAB v4.2.1 high-confidence regions, computed by
  `hap.py` using the **`xcmp`** engine against the GIAB HG002 truth VCF + BED, recorded per run
  as `validation_pass`. INDEL performance is reported for information only and is not gated.
  Any change to reference, caller or filtering re-triggers validation before tagging.
- current evidence: measured 2026-07-15 — HaplotypeCaller SNV precision 0.9934, recall 0.9894,
  F1 0.9914, INDEL F1 0.9971, Ti/Tv 2.07, mean depth 255.8x — on chr20:1,000,000-2,000,000.
  See WARNING W3: the measured window is narrower than ADR-0001's locked chr20 scope.

## C-arch-implementation-status — Task plan state
- source: `.kiro/specs/clinical-genomics-platform/tasks.md`
- type: architecture
- constraint / note: all 17 tasks are marked complete `[x]` — metadata stack, IAM stack,
  orchestration stack, observability stack, CDK app entry point, 7 Lambda handlers, RAG layer
  (FAISS + retrieval), DynamoDB-to-Postgres sync, property-based tests, updated CDK guardrail
  tests asserting no Batch/Fargate/NAT/RDS, CI updates, and production migration
  documentation. The task plan predates ADRs 0013-0016 and contains no tasks for the QC
  warning layer, the agentic interpreter, the xcmp engine switch or the tiered CI/CD.
