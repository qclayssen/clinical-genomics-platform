# Requirements (extracted)

No PRD-classified documents exist in this ingest set. Requirements are extracted from the
single EARS-style requirements SPEC plus requirements introduced by locked ADRs that the SPEC
predates.

Primary source: `.kiro/specs/clinical-genomics-platform/requirements.md` (SPEC, 15 numbered
requirements with acceptance criteria).
Secondary sources: ADR-0013, ADR-0014, ADR-0015, ADR-0016 (all LOCKED, precedence 0) — these
postdate the SPEC and extend or override it. Where they do, the ADR text is authoritative.

---

## REQ-pipeline-execution
- source: SPEC `.kiro/specs/clinical-genomics-platform/requirements.md` §Requirement 1
- description: A modular Nextflow DSL2 pipeline processes GIAB HG002 chr20 paired-end FASTQ
  through QC, alignment, variant calling and validation with full provenance.
- acceptance criteria:
  1. Stage order: fastp trimming -> FastQC -> BWA-MEM2 alignment -> MarkDuplicates ->
     variant calling (selected caller) -> hap.py validation -> structured export (JSON and
     Parquet) -> MultiQC aggregation.
  2. MultiQC HTML report aggregates fastp, FastQC, MarkDuplicates and hap.py outputs.
  3. Validation computes SNV precision, recall, F1 against the truth set and records
     `validation_pass = true` iff SNV F1 >= 0.99.
  4. `metrics.json` embeds a provenance stamp: git commit SHA, pipeline version, caller
     version, reference genome version, truth set version, SHA-256 of all inputs.
  5. `-stub` completes all process stubs with zero failures, no tool containers, no real data.
  6. Non-retryable failure emits a structured error (process name, exit code, stderr);
     retryable exit codes (137, 143, 104, 134, 139) retry up to 2 times first.
  7. One process per module file, nf-core convention, every process specifies a container.
  8. Caller selectable between HaplotypeCaller and DeepVariant, defaulting to HaplotypeCaller.
- ADR overlay: ADR-0013 (LOCKED) inserts a new `QC_EVALUATE` process **after**
  `HAPPY_BENCHMARK` emitting `qc_warnings.json`; the stage order above is extended, not
  replaced. ADR-0015 (LOCKED) fixes the hap.py engine to `xcmp`.
- scope: pipeline

## REQ-serverless-orchestration
- source: SPEC §Requirement 2
- description: Cloud execution orchestrated by Step Functions + Lambda instead of
  Batch/Fargate, staying inside AWS free-tier limits at demo scale.
- acceptance criteria:
  1. State machine states in order: trigger ingestion, QC checks, variant calling, validate
     results, export to data lake, ingest metadata to DynamoDB, generate AI report.
  2. One Lambda per state; memory <= 512 MB; timeout <= 15 minutes per invocation.
  3. On success, an audit record with `run_id`, action `WORKFLOW_COMPLETE`, execution start,
     execution end, ISO 8601 completion timestamp.
  4. Lambda failure retries up to 2 times, exponential backoff, 5s initial interval,
     backoff rate 2.0, before a failure state.
  5. On failure state: SNS notification plus an audit record with `run_id`, action
     `WORKFLOW_FAILED`, failed state name, error cause, ISO 8601 timestamp.
  6. Least-privilege IAM roles scoped to only the resources each function accesses.
  7. State machine maximum concurrency of 1.
- ADR overlay: ADR-0013 (LOCKED) adds Step Functions Choice states for failure-pattern routing,
  a healer Lambda, a CheckHealingLimit guard, and a notify-then-wait state. The seven-state
  list above is extended, not replaced.
- scope: cloud orchestration

## REQ-eventbridge-automation
- source: SPEC §Requirement 3
- description: New FASTQ uploads to S3 automatically trigger the analysis workflow.
- acceptance criteria:
  1. Object created under `raw/` (including nested prefixes) with `.fastq.gz` or `.fq.gz`
     (case-insensitive) starts a Step Functions execution within 60 seconds.
  2. Rule passes S3 bucket name, object key and object size to the execution.
  3. Objects under `raw/` without those extensions do not start an execution.
  4. Retry policy of 3 attempts with exponential backoff; DLQ with 14-day retention.
  5. A new object version for an existing `raw/` key starts a new execution (no dedup).
  6. DLQ depth >= 1 triggers a CloudWatch alarm.
- scope: event-driven trigger

## REQ-s3-data-lake
- source: SPEC §Requirement 4
- description: S3 data lake with versioning, encryption, lifecycle policies.
- acceptance criteria:
  1. SSE-S3 (AES-256) default encryption.
  2. TLS enforced via bucket policy Deny on `aws:SecureTransport = false`.
  3. Versioning enabled; overwrites create versions, no prior version removed.
  4. All four Block Public Access settings enabled.
  5. Lifecycle: current-version objects under `work/` expire after 14 days.
  6. Lifecycle: `raw/` transitions to IA at 30 days, Glacier at 180 days.
  7. Removal policy RETAIN — `cdk destroy` does not delete the bucket or contents.
- ADR alignment: this is the surviving, non-superseded portion of ADR-0004.
- scope: storage

## REQ-dynamodb-metadata-store
- source: SPEC §Requirement 5
- description: Run metadata, QC metrics, provenance and audit trail in DynamoDB on-demand.
- acceptance criteria:
  1. PAY_PER_REQUEST billing; removal policy RETAIN.
  2. PK `run_id` (String), SK `record_type` (String) restricted to RUN, QC_METRICS,
     PROVENANCE, AUDIT, CORRECTION — single-table design.
  3. GSI PK `sample_id`, SK `created_at`.
  4. Every record carries `created_at` as ISO 8601 UTC, seconds precision.
  5. Append-only enforced by IAM deny of `dynamodb:DeleteItem` and `dynamodb:UpdateItem`
     for all Lambda roles.
  6. PROVENANCE records contain input FASTQ SHA-256s, pipeline version, caller tool+version,
     reference build+version, truth set version.
  7. Corrections insert a new `CORRECTION` record with `original_record_type`,
     `correction_reason` and corrected values, leaving the original unchanged.
  8. Point-in-time recovery enabled.
  9. Failed writes retry up to 3 times with exponential backoff; on exhaustion publish to the
     CloudWatch alarm topic and transition the workflow to a failure state.
- ADR overlay: ADR-0013 (LOCKED) adds a `QC_WARNING` record type. The enum in criterion 2 is
  extended to {RUN, QC_METRICS, PROVENANCE, AUDIT, CORRECTION, QC_WARNING}.
- scope: primary datastore

## REQ-observability
- source: SPEC §Requirement 6
- description: CloudWatch logs, metrics and alarms for all Lambdas and Step Functions.
- acceptance criteria:
  1. Structured JSON logs, 30-day retention, each entry with timestamp, log level, run_id,
     function name, message.
  2. Alarm on Step Functions `ExecutionsFailed` >= 1 within a 1-minute evaluation period.
  3. Alarm on any Lambda error rate > 5% over 5 minutes with >= 10 invocations, missing data
     treated as `notBreaching`.
  4. All alarms publish to an SNS topic on entering ALARM.
  5. Alarm on `ExecutionTime` when an execution exceeds 30 minutes.
- ADR overlay: ADR-0013 (LOCKED) adds 6 QC metric alarms in the `CGP/QC` namespace with SNS
  actions.
- scope: observability

## REQ-iam-least-privilege
- source: SPEC §Requirement 7
- description: All IAM policies scoped to minimum necessary permissions.
- acceptance criteria:
  1. A separate role per Lambda, scoped to specific S3 prefixes, DynamoDB actions and Step
     Functions actions.
  2. Explicit deny on `dynamodb:DeleteItem`, `dynamodb:UpdateItem`, `dynamodb:DeleteTable`
     on the metadata table for all Lambda roles.
  3. Explicit deny on `s3:DeleteObject` and `s3:DeleteObjectVersion` for `raw/*` and
     `results/*`, with no exception for any Lambda role.
  4. CDK guardrail tests assert no Lambda-role policy grants `*` as a resource ARN or any
     `iam:*` action.
  5. No Lambda role includes `iam:CreatePolicy`, `iam:AttachRolePolicy`, `iam:PutRolePolicy`
     or `sts:AssumeRole`.
- scope: security

## REQ-metabase-dashboard
- source: SPEC §Requirement 8
- description: Metabase dashboard showing cohort QC trends, turnaround times, failure rates.
- acceptance criteria:
  1. Time-series of mean SNV F1 grouped by pipeline version and caller; version on x, F1
     (0.0-1.0) on y.
  2. Turnaround time chart: elapsed minutes run-start to export-complete for the 20 most
     recent runs, ordered by start time descending.
  3. Pass/fail ratio over a configurable window of 7, 30 or 90 days, defaulting to 30.
  4. Duplication rate bar chart, percent duplication 0.0-100.0 per sample, descending.
  5. A run ingested into DynamoDB is reflected in the dashboard within 5 minutes.
  6. Runs in a local Docker container via docker-compose.
  7. Empty-state message when no data exists for the selected window.
- ADR overlay: ADR-0013 (LOCKED) adds three views — warning frequency, metric vs threshold,
  quarantine status.
- scope: BI

## REQ-rag-reporting
- source: SPEC §Requirement 9
- description: AI-drafted reports enriched with gene/variant annotation context from a local
  knowledge base, with no paid cloud AI.
- acceptance criteria:
  1. Local vector store (FAISS or ChromaDB) over gene annotations, variant significance DBs
     and mutational signature descriptions, >= 1 entry per gene in the target region.
  2. Retrieve up to 5 passages, each <= 512 tokens, ranked by cosine similarity, only
     passages scoring >= 0.70.
  3. Fewer than 5 qualifying passages (including zero) proceeds without error.
  4. Passages plus `metrics.json` go to a local open-source LLM (Ollama or HF transformers)
     producing 120-300 words.
  5. Entirely local compute; no Bedrock, no paid SageMaker endpoints.
  6. Guardrails engine enforces the `AI-DRAFTED — REQUIRES CLINICIAN REVIEW` banner, a
     provenance citation line, and scrubbing of recommendation phrasing.
  7. Local LLM failing within 120 seconds or raising any runtime error falls back to the
     deterministic offline template renderer with a warning logged.
- ADR alignment: criteria 6 restates ADR-0008 (LOCKED), which remains the authoritative
  statement of the guardrail contract.
- scope: AI reporting

## REQ-lora-finetuning
- source: SPEC §Requirement 10
- description: QLoRA fine-tuning of a small open LLM on free-tier compute.
- acceptance criteria:
  1. Model <= 3B parameters, 4-bit QLoRA adapters, peak GPU memory <= 12 GB VRAM.
  2. Paired metrics.json -> report JSONL training data, minimum 10 examples.
  3. PEFT-compatible adapter weights loadable via `PeftModel.from_pretrained` without
     reloading the full base model.
  4. CPU-only smoke test completing in under 5 minutes, full loop on >= 5 sample pairs,
     saved adapter, >= 1 generated token.
  5. Runs on free compute (Colab, Kaggle, SageMaker Studio Lab, local CPU/GPU); no paid AWS.
  6. Model card records learning rate, batch size, gradient accumulation steps, epochs,
     LoRA rank, LoRA alpha, dataset version, base model identifier, final training loss.
  7. Failed/interrupted training exits non-zero and does not overwrite a prior checkpoint.
- ADR alignment: consistent with ADR-0007 (LOCKED).
- scope: ML

## REQ-provenance-audit
- source: SPEC §Requirement 11
- description: Every result carries a full provenance stamp; every system action is recorded
  in an append-only audit trail (ISO 15189 traceability pattern).
- acceptance criteria:
  1. Provenance stamp per run: git commit SHA (40-char hex), pipeline version (semver),
     caller tool name and version, reference build identifier and version, truth set version,
     SHA-256 of all input FASTQs — as a JSON object inside `metrics.json`.
  2. On pipeline completion, an audit entry within 30 seconds: action `PIPELINE_COMPLETE`,
     run_id, ISO 8601 UTC timestamp.
  3. On AI report generation, an audit entry: action `REPORT_DRAFTED`, run_id, model version,
     adapter version (or `null` for zero-shot fallback), ISO 8601 UTC timestamp.
  4. Update/delete of audit entries rejected via IAM deny, returning Access Denied.
  5. SNV F1 strictly below 0.99 marks `validation_pass: false` and writes an audit entry with
     action `VALIDATION_FAILED`, run_id and observed F1.
  6. Audit write failing after 3 retries publishes a CloudWatch alarm notification and
     transitions the workflow to a failure state without discarding the pending audit data.
- ADR overlay: ADR-0010 (LOCKED) adds the not-yet-wired `ga4gh:SQ.` reference identifier to
  run provenance alongside `reference_build`.
- scope: provenance, audit

## REQ-docker-containerization
- source: SPEC §Requirement 12
- description: Every pipeline stage and platform component containerized with pinned images.
- acceptance criteria:
  1. Container directive on every Nextflow process, pinned by sha256 digest where the registry
     supports Content Trust, by exact version tag otherwise.
  2. Biocontainers (quay.io/biocontainers) for BWA-MEM2, GATK, hap.py, samtools, bcftools,
     fastp, FastQC, MultiQC, DeepVariant.
  3. Lambdas packaged as container images from a version-controlled Dockerfile whose base
     image is pinned by sha256 digest.
  4. Metabase runs from a docker-compose service pinned to an exact release tag.
  5. RAG reporter runs in a single container containing the vector store, LLM runtime and
     inference code.
  6. Every dependency installation step pins exact versions (lock file or explicit specifier).
- **ADR override:** ADR-0009 (LOCKED) requires digest pinning in production and explicitly
  rejects tag pinning. Criterion 1's "exact version tag" exemption is narrowed to
  non-production/registry-limited cases only; criterion 4 (Metabase by tag) is a
  non-pipeline component and outside ADR-0009's "every pipeline step" scope.
- scope: reproducibility

## REQ-cicd
- source: SPEC §Requirement 13
- description: GitHub Actions workflows lint, test and validate all components on every push.
- acceptance criteria:
  1. Pipeline changes run Nextflow config validation and nf-core lint, within 10 minutes.
  2. Pipeline changes run `nextflow run -stub`, within 10 minutes.
  3. Infrastructure changes run `tsc --noEmit` and `cdk synth --all`, within 10 minutes.
  4. Pipeline/ai-report/db changes run `pytest tests/` plus AI guardrail validation
     (provenance metadata and clinician-review banner present), within 10 minutes.
  5. ai-report changes run `train_smoke.py` completing >= 1 training step, within 15 minutes.
  6. Any failing job marks the status check failed, blocking merge via branch protection.
  7. All workflow jobs request only `contents: read`.
- **ADR override:** ADR-0016 (LOCKED, precedence 0) supersedes criterion 7. The tiered
  strategy requires elevated permissions on specific workflows — `issues: write`
  (maintenance.yml), SARIF upload (security-events), GHCR push (packages), coverage PR
  comments, and release creation. See REQ-cicd-tiers.
- scope: CI/CD

## REQ-cost-guardrails
- source: SPEC §Requirement 14
- description: Guardrail tests verify all AWS resources stay within free-tier limits.
- acceptance criteria:
  1. DynamoDB on-demand (25 WCU/25 RCU equivalent, 25 GB always-free).
  2. All Lambdas memory <= 512 MB, timeout <= 15 minutes.
  3. **No AWS Batch, Fargate, NAT Gateways or RDS instances provisioned.**
  4. No Bedrock, SageMaker, Comprehend, Rekognition or Kendra resources provisioned.
  5. CDK guardrail tests assert zero resources of types `AWS::Batch::*`, `AWS::ECS::Service`,
     `AWS::EC2::NatGateway`, `AWS::RDS::*`, `AWS::Bedrock::*`, `AWS::SageMaker::Endpoint`,
     `AWS::Kendra::*`, `AWS::Comprehend::*`.
  6. CloudWatch billing alarm on `EstimatedCharges` in `AWS/Billing`, ALARM above $1 USD,
     single 6-hour period, publishing to SNS.
  7. No more than 4,000 Step Functions state transitions per month at demo scale.
- ADR alignment: restates the cost backstops of ADR-0011 (LOCKED).
- **open tension:** criterion 3 combined with ADR-0011's stated Lambda limitation leaves no
  built cloud substrate for real genomics compute. See WARNING W1 in `INGEST-CONFLICTS.md`.
- scope: cost

## REQ-production-migration-docs
- source: SPEC §Requirement 15
- description: Documentation describing how each free-tier component maps to a production
  AWS service.
- acceptance criteria:
  1. AWS HealthOmics documented as the production path for pipeline execution, including how
     the Nextflow workflow maps to HealthOmics private workflows.
  2. Aurora Serverless documented as the production replacement for DynamoDB when relational
     query patterns are needed.
  3. Amazon Bedrock with guardrails documented as the production replacement for local RAG.
  4. SageMaker documented as the production fine-tuning platform.
  5. Cost and operational trade-offs documented for each production alternative.
- evidence: `docs/PRODUCTION-MIGRATION.md` satisfies all five criteria (verified during
  synthesis — it contains the HealthOmics, Aurora Serverless v2, Bedrock + Knowledge Bases and
  SageMaker Training sections plus a cost/trade-off table).
- scope: documentation

---

# ADR-derived requirements (postdate the SPEC)

## REQ-qc-warnings-self-healing
- source: ADR-0013 `docs/adr/0013-qc-warnings-adaptive-thresholds-self-healing.md` (LOCKED)
- description: A QC warning layer with adaptive thresholds, multi-level self-healing and
  notify-then-auto-execute remediation, replacing binary pass/fail as the only quality signal.
- acceptance criteria:
  1. Six metrics monitored (percent_duplication, q30_rate, reads_filtered_percent, snp_f1,
     snp_precision, snp_recall), each with warn and fail thresholds and direction semantics.
  2. `pipeline/conf/qc_thresholds.yaml` is the single source of truth; schema-validated with
     meaningful error messages, covered by property tests.
  3. `QC_EVALUATE` Nextflow process runs after `HAPPY_BENCHMARK` and emits `qc_warnings.json`.
  4. Adaptive thresholds computed as mean +/- 2σ when >= 20 historical runs exist; below 20
     runs use bootstrap defaults; σ=0 falls back to bootstrap; thresholds clamped to [0,1].
  5. Retry profiles apply progressively stricter fastp parameters per attempt
     (phred 15->20->25, length 50->60->75).
  6. Quarantine escalates: soft on first failure (blocks reports), hard on consecutive
     failures (moves data, full block); an explicit `release_quarantine` admin action exists.
  7. Step Functions Choice states route known failure patterns deterministically
     (OOM -> more memory, timeout -> longer duration, QC breach -> stricter params).
  8. Healer Lambda produces an Ollama-based diagnosis with a rule-based fallback, constrained
     to a fixed action set with response validation.
  9. After a healer recommendation: SNS notification, configurable wait (default 10 minutes),
     then auto-execution; operators may approve or override.
  10. Maximum 2 self-healing attempts, enforced by a CheckHealingLimit guard.
  11. Warnings surface in CloudWatch (6 alarms, `CGP/QC` namespace), MultiQC conditional
      formatting, DynamoDB `QC_WARNING` records, and three Metabase views.
- scope: QC, remediation
- open question: the healer Lambda's LLM runtime placement versus the <= 512 MB / <= 15 min
  Lambda envelope is unstated. See WARNING W2 in `INGEST-CONFLICTS.md`.

## REQ-variant-interpretation
- source: ADR-0014 `docs/adr/0014-agentic-variant-interpretation.md` (LOCKED)
- description: ReAct-style agentic ACMG/AMP variant interpretation with deterministic fallback
  and multi-provider LLM support.
- acceptance criteria:
  1. ReAct loop (`react.py`) reasons, dispatches tool calls, observes and iterates to a final
     ACMG/AMP 2015 five-tier classification.
  2. Every thought, tool call and observation is traced and auditable.
  3. Deterministic fallback (`deterministic.py`) always produces a classification when the LLM
     is unavailable, loops, or exceeds budget; it never claims Pathogenic without strong
     ClinVar evidence.
  4. `llm.py` supports Ollama, OpenAI and Anthropic with an automatic fallback chain, plus a
     `DeterministicBackend` used in CI.
  5. `data/chr20_knowledge.db` (SQLite, ClinVar + gnomAD chr20 subsets) makes the agent work
     offline and in CI with zero external API calls.
  6. Safety constraints enforced in code, not prompts: no treatment language, mandatory VUS
     uncertainty flags, review banner, evidence citations required.
  7. Scoped to chr20 only, matching ADR-0001.
- scope: AI interpretation

## REQ-validation-engine-xcmp
- source: ADR-0015 `docs/adr/0015-happy-xcmp-engine-not-vcfeval.md` (LOCKED)
- description: hap.py benchmarking runs on the default `xcmp` engine, not vcfeval.
- acceptance criteria:
  1. `HAPPY_BENCHMARK` invokes hap.py without `--engine vcfeval`, using the self-contained
     `xcmp` engine in the pinned biocontainers image.
  2. `docs/VALIDATION.md` and all other docs state `xcmp`, not vcfeval.
  3. The SNV F1 >= 0.99 acceptance criterion and truth-set methodology of ADR-0003 are
     unchanged.
- evidence: `docs/VALIDATION.md` already states the xcmp engine and cites ADR-0015 — verified
  during synthesis, so this requirement is satisfied in documentation.
- scope: validation

## REQ-cicd-tiers
- source: ADR-0016 `docs/adr/0016-cicd-strategy.md` (LOCKED)
- description: Three-tier GitHub Actions CI/CD covering lint, security scanning, DB
  validation, coverage, container lifecycle and release engineering.
- acceptance criteria:
  1. Tier 1 (every push, < 3 min): `lint.yml` (Ruff + tsc), `security.yml` pip-audit job,
     `pipeline-ci.yml` (Nextflow stub, unit tests with coverage, lambda imports).
  2. Tier 2 (on PR/merge, ~10 min): `security.yml` trivy-repo job with SARIF upload,
     `db-ci.yml`, `docker.yml` (build + Trivy + GHCR sha-tagged push), `coverage.yml`
     (PR delta comment, badge update on main).
  3. **`db-ci.yml` MUST machine-verify and block on: schema apply, migration idempotency,
     seed data, and immutability trigger tests.** These are explicitly called out as proving
     schema integrity "machine-verified, not trust-based".
  4. Tier 3: `maintenance.yml` (weekly Trivy + license compliance, auto-issue on failure),
     `release.yml` (tag-triggered Release + versioned image), Dependabot weekly across pip,
     npm, GitHub Actions and Docker ecosystems.
  5. **Every PR produces 6 or more status checks.**
  6. Total tooling cost $0; all free-tier.
  7. License compliance guards the MIT codebase against GPL contamination.
- scope: CI/CD
- coverage gap: criterion 3's immutability trigger tests exercise Postgres — which ADR-0012
  demoted to a read-replica. See WARNING W4 in `INGEST-CONFLICTS.md`.
