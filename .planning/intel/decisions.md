# Decisions (ADR intel)

Synthesized from 16 ADRs in `docs/adr/`. Precedence: ADR > SPEC > PRD > DOC.
ADRs 0013-0016 carry an explicit per-doc precedence override of `0` (highest).

Status key: **LOCKED** = Accepted and authoritative. **SUPERSEDED** = no longer
authoritative for the superseded portion. **PARTIAL** = only part of the ADR was superseded.

---

## ADR-0001 — Scope to GIAB HG002, chromosome 20, germline SNVs
- source: `docs/adr/0001-scope-giab-hg002-chr20.md`
- status: **LOCKED** (Accepted, 2026-05-01)
- decision: Restrict v1 to sample GIAB HG002 / NA24385; region chromosome 20 only
  (a ~1 Mb slice reserved for the CI/test profile); analysis germline SNV calling only.
  INDELs, whole genome, somatic calling and immune repertoire are explicitly out of scope
  for v1 and marked designed-for extensions.
- scope: project scope, sample selection, region, variant class
- accepted limitations: performance claimed on chr20 only; INDEL performance reported for
  information but not gated.

## ADR-0002 — Nextflow DSL2 (nf-core style) for the pipeline
- source: `docs/adr/0002-nextflow-dsl2-pipeline.md`
- status: **LOCKED** (Accepted, 2026-05-03)
- decision: Implement the pipeline in Nextflow DSL2 following nf-core conventions — one
  process per module file, `test`/`aws` profile split, container-per-process, captured run
  provenance (timeline, trace, DAG).
- scope: pipeline framework, module layout, profiles, provenance capture
- note: the ADR's Consequences section cites "runs unchanged on AWS Batch"; that clause is
  stale following ADR-0011. The DSL2/nf-core decision itself is unaffected.

## ADR-0003 — Validate by benchmarking against a truth set (hap.py)
- source: `docs/adr/0003-truth-set-validation.md`
- status: **LOCKED (PARTIAL)** — Accepted; **engine choice superseded by ADR-0015**
- decision (authoritative): Truth-set benchmarking is a first-class pipeline stage. Compare
  each run's VCF to the GIAB HG002 v4.2.1 benchmark using `hap.py`, restricted to the
  published high-confidence BED, computing precision, recall and F1. Explicit acceptance
  criterion **SNV F1 >= 0.99**, recorded per run as `validation_pass`.
- decision (superseded): the comparison engine `vcfeval` — replaced by `xcmp` per ADR-0015.
- scope: validation methodology, acceptance criterion, truth set version, high-confidence BED
- rejected alternatives (still in force): no formal validation; `bcftools isec` overlap;
  a fixed threshold with no truth set.

## ADR-0004 — Deploy on AWS via CDK + Batch/Fargate
- source: `docs/adr/0004-aws-cdk-batch-fargate.md`
- status: **SUPERSEDED (PARTIAL)** by ADR-0011 — compute choice only
- decision (still authoritative): all infrastructure as code via AWS CDK (TypeScript);
  an S3 data-lake stack; scoped IAM; CloudWatch observability; `cdk synth` in CI; Jest
  guardrail tests encoding accreditation-relevant invariants (bucket versioning,
  public-access block, TLS-only, deny-delete on raw/results).
- decision (superseded by ADR-0011): compute on AWS Batch running on Fargate.
- scope: IaC tooling, stack decomposition, S3 data lake, IAM, guardrail tests

## ADR-0005 — Insert-only PostgreSQL schema
- source: `docs/adr/0005-insert-only-postgres.md`
- status: **SUPERSEDED** by ADR-0012
- decision (superseded as primary store): PostgreSQL with insert-only tables `runs`,
  `qc_metrics`, `run_provenance`, `audit_log`; UPDATE/DELETE blocked by DB triggers
  (`forbid_mutation()`); corrections are new rows; every ingestion writes an `audit_log` entry.
- what survives: the **"amend, never erase"** semantic is explicitly carried forward by
  ADR-0012, and Postgres itself is retained as the Metabase read-replica. The
  trigger-enforced, database-level immutability guarantee does **not** survive for the
  primary store — see the honest tradeoff in ADR-0012.
- scope: metadata storage, tamper-evidence, audit trail

## ADR-0006 — Metabase for the operational dashboard
- source: `docs/adr/0006-metabase-dashboard.md`
- status: **LOCKED** (Accepted, 2026-05-17)
- decision: Metabase (open-source) connected to the results Postgres. Every dashboard card is
  committed SQL reading from a `v_run_summary` view. `docker-compose.yml` brings up
  Postgres + Metabase with a demo seed so the dashboard renders before any real run.
- scope: BI/dashboard layer, dashboard reproducibility

## ADR-0007 — Fine-tune a small open model with QLoRA (PyTorch)
- source: `docs/adr/0007-qlora-small-open-model.md`
- status: **LOCKED** (Accepted, 2026-05-21)
- decision: Fine-tune a small open-weight instruction model (Llama-3.2-3B-Instruct or
  Phi-3-mini) with QLoRA — 4-bit quantization + LoRA adapters via `peft`/`trl` — sized for a
  single ~10-12 GB GPU. Two supporting paths are mandatory: a CPU smoke test
  (`train_smoke.py`) that runs the identical loop on a tiny model, and a prompt-engineered
  fallback plus dependency-free offline renderer.
- scope: ML stack, fine-tuning method, degradation chain (fine-tuned -> fallback -> offline)

## ADR-0008 — Enforce AI guardrails and human-in-the-loop in code
- source: `docs/adr/0008-guardrails-human-in-the-loop.md`
- status: **LOCKED** (Accepted, 2026-05-24)
- decision: Model output is untrusted and must pass a deterministic, unskippable
  `enforce_guardrails()` step: mandatory `AI-DRAFTED — REQUIRES CLINICIAN REVIEW` banner
  (re-inserted if missing), mandatory provenance line, advice-phrase scrubbing to
  `[review required]`, required field-level citations. The model never sees raw reads or the
  VCF body — only structured metrics. A qualified human signs off every report.
- scope: AI safety, output contract, human-in-the-loop

## ADR-0009 — Containerise every step and pin images by digest
- source: `docs/adr/0009-docker-pinned-by-digest.md`
- status: **LOCKED** (Accepted, 2026-05-27)
- decision: Every pipeline step runs in its own container (Biocontainers where available),
  pinned by immutable digest (`@sha256:...`) in production, never by mutable tag. The local
  helper image (`docker/Dockerfile.tools`) is pinned the same way. Container identity is
  captured in each run's provenance. A tool upgrade is a deliberate digest change that
  re-triggers validation.
- scope: containerization, reproducibility, provenance
- explicitly rejected: pinning by version tag; conda/mamba without containers; a single fat image.

## ADR-0010 — Align with GA4GH interoperability standards
- source: `docs/adr/0010-ga4gh-standards-alignment.md`
- status: **LOCKED** (Accepted, 2026-07-14)
- decision: Adopt GA4GH incrementally and honestly. Implement now: the `sha512t24u`
  computed-digest primitive (shared by refget and VRS), dependency-free, verified against the
  VRS spec known-answer vector, producing `ga4gh:SQ.<digest>` reference identifiers. Document
  the rest (VRS alleles, WES, DRS, Phenopackets, htsget, service-info, Crypt4GH, Passport/DUO)
  in `docs/GA4GH-ALIGNMENT.md` marked Implemented / Partial / Aspirational / N/A. Chosen next
  step (not yet wired): record `ga4gh:SQ.` in run provenance alongside `reference_build`.
- scope: standards alignment, reference identity, provenance

## ADR-0011 — Migrate compute from Batch/Fargate to serverless (Lambda + Step Functions)
- source: `docs/adr/0011-serverless-lambda-stepfunctions.md`
- status: **LOCKED** (Accepted, 2026-07-15) · Supersedes ADR-0004 (compute choice only)
- decision: Replace the Batch/Fargate `compute-stack` with an `orchestration-stack`:
  a Step Functions state machine (`maxConcurrency: 1`) driving 7 Lambdas (ingestion-trigger ->
  qc-orchestrator -> variant-calling -> validation-checker -> export-handler ->
  metadata-ingestor -> report-generator), each with retry (2x, 5s, backoff 2.0); an
  EventBridge rule on S3 `raw/*.fastq.gz` -> `StartExecution`; a 14-day SQS DLQ; SNS for
  alarms; everything sized to the AWS always-free tier; a `> $1` billing alarm; and a CI check
  asserting zero Batch/Fargate/NAT/RDS/Bedrock/SageMaker resources in synthesized templates.
- explicitly retained from ADR-0004: IaC via CDK reviewed in CI, data-classification tagging,
  and the S3 data lake.
- **stated limitation:** Lambda (<=512 MB, <=15 min, no GPU) **cannot run real genomics tools**
  (BWA-MEM2, DeepVariant, hap.py) on real WGS data. The Lambda path is an orchestration
  demonstration; actual heavy compute runs via the local Nextflow pipeline. The production
  migration path (AWS HealthOmics) is documented, not built.
- scope: cloud compute, orchestration, event-driven trigger, cost posture

## ADR-0012 — DynamoDB as the primary metadata store (Postgres demoted to read-replica)
- source: `docs/adr/0012-dynamodb-primary-store.md`
- status: **LOCKED** (Accepted, 2026-07-15) · Supersedes ADR-0005
- decision: DynamoDB becomes the primary metadata store. Single table `cgp-metadata`:
  PK `run_id`, SK `record_type` in {RUN, QC_METRICS, PROVENANCE, AUDIT, CORRECTION}; GSI
  `sample_id-created_at-index`; `PAY_PER_REQUEST`; Point-in-Time Recovery on; `RETAIN`.
  Append-only is enforced by **IAM deny** of `dynamodb:DeleteItem` / `dynamodb:UpdateItem` on
  every Lambda role; a correction is a new `CORRECTION` item. Postgres stays as the Metabase
  read-replica fed by the metadata ingestor, so `v_run_summary` and the dashboard keep working.
- **explicitly acknowledged regression:** the immutability guarantee gets weaker. Postgres
  `forbid_mutation()` was a data-level, unbypassable control; DynamoDB append-only rests on
  IAM, a perimeter control bypassable by a table admin or account root. Compensating detective
  controls: (1) PITR, (2) DynamoDB Streams -> append-only audit sink (e.g. S3 object-lock) so
  MODIFY/REMOVE is detectable out-of-band, (3) writes restricted to the 7 scoped Lambda roles.
- scope: primary datastore, immutability model, BI bridge

## ADR-0013 — QC warnings with adaptive thresholds and self-healing
- source: `docs/adr/0013-qc-warnings-adaptive-thresholds-self-healing.md`
- status: **LOCKED** (Accepted, 2026-07-15) · precedence override: 0
- decision, four capabilities:
  1. **Multi-metric threshold evaluation** — 6 metrics (percent_duplication, q30_rate,
     reads_filtered_percent, snp_f1, snp_precision, snp_recall), each with warn/fail
     thresholds and direction semantics (higher_is_worse / lower_is_worse). Single source of
     truth `pipeline/conf/qc_thresholds.yaml`. New Nextflow process `QC_EVALUATE` runs after
     `HAPPY_BENCHMARK`, emitting `qc_warnings.json`.
  2. **Adaptive thresholds (mean +/- 2σ)** — computed from run history when >= 20 historical
     runs exist; below that, bootstrap defaults from config. σ=0 falls back to bootstrap;
     thresholds clamped to [0,1].
  3. **Multi-level self-healing** — progressively stricter fastp retry profiles
     (phred 15->20->25, length 50->60->75); escalating quarantine (soft on first failure,
     blocks reports; hard on consecutive failures, moves data and fully blocks); Step Functions
     Choice states for known failure patterns (OOM -> more memory, timeout -> longer duration,
     QC breach -> stricter params); an Ollama-based AI healer Lambda with rule-based fallback.
  4. **Notify-then-auto-execute** — SNS notification with proposed action, configurable wait
     (default 10 minutes), then automatic remediation. Maximum 2 self-healing attempts before
     escalation (CheckHealingLimit guard).
- warning surfaces: 6 CloudWatch alarms in the `CGP/QC` namespace with SNS actions; MultiQC
  conditional formatting; DynamoDB `QC_WARNING` records; three Metabase views (warning
  frequency, metric vs threshold, quarantine status).
- risks explicitly mitigated: infinite healing loops (max 2 attempts); LLM hallucination
  (fixed action set + response validation + rule-based fallback); hard-quarantine lock-in
  (explicit `release_quarantine` admin action); threshold misconfiguration (schema validation
  + property tests).
- claimed test posture: 212 Python tests + 66 CDK tests.
- scope: QC monitoring, remediation, quarantine, alarm surfaces, DynamoDB record types

## ADR-0014 — Agentic variant interpretation with a ReAct loop
- source: `docs/adr/0014-agentic-variant-interpretation.md`
- status: **LOCKED** (Accepted, 2026-07-15) · precedence override: 0
- decision: Implement a ReAct-style agentic loop (Thought -> Action -> Observation -> Answer)
  for ACMG/AMP 2015 five-tier variant classification, with:
  1. **ReAct agent** (`react.py`) — LLM chooses and dispatches tool calls, observes, iterates.
  2. **Deterministic fallback** (`deterministic.py`) — fixed pipeline (ClinVar -> gnomAD ->
     ACMG rules -> template report) guaranteeing a classification is always produced when the
     LLM is unavailable, loops, or exceeds budget.
  3. **Multi-provider LLM** (`llm.py`) — Ollama (local), OpenAI, Anthropic with an automatic
     fallback chain; `DeterministicBackend` for CI.
  4. **Local-first data** (`data/chr20_knowledge.db`) — SQLite with ClinVar + gnomAD chr20
     subsets so the agent works offline and in CI with no external API calls.
  5. **Safety constraints enforced in code, not prompts** — no treatment language, mandatory
     VUS uncertainty flags, review banner, evidence citations required.
- scope alignment: chr20 only, matching ADR-0001. Extends the ADR-0008 guardrails pattern to
  variant-level interpretation. Explicitly not a production clinical tool.
- accepted limitations: classifications bounded by a 15-record local ClinVar subset; automated
  ACMG evidence cannot cover criteria needing clinical data (PS2 de novo, PP1 segregation);
  ~5 LLM calls per variant makes it unsuitable for real-time use.

## ADR-0015 — Use hap.py's xcmp engine, not vcfeval
- source: `docs/adr/0015-happy-xcmp-engine-not-vcfeval.md`
- status: **LOCKED** (Accepted, 2026-07-15) · precedence override: 0
- supersedes: the **engine choice only** in ADR-0003.
- decision: Run `hap.py` with its default **`xcmp`** engine instead of `--engine vcfeval`.
  Driver: the pinned container `quay.io/biocontainers/hap.py:0.3.15--py27hcb73b3d_0` does not
  bundle `rtg-tools`, which vcfeval requires — the process failed with `rtg: command not
  found` on any host architecture. The historical `pkrusche/hap.py` image that does bundle
  rtg-tools uses a legacy manifest format modern Docker refuses to pull.
  `docs/VALIDATION.md`, the `HAPPY_BENCHMARK` module, and other vcfeval references are
  updated to `xcmp`.
- explicitly unaffected: benchmarking as a first-class stage, the SNV F1 >= 0.99 acceptance
  criterion and its interpretation, and ADR-0003's rejected alternatives.
- accepted limitation: `xcmp` representation-matching is less sophisticated than vcfeval's for
  complex/nearby variants and can be slightly more conservative; not expected to matter at
  chr20 SNV scale. Switching back is a one-line change plus a new ADR if an image bundling
  both becomes available.

## ADR-0016 — Tiered CI/CD strategy
- source: `docs/adr/0016-cicd-strategy.md`
- status: **LOCKED** (Accepted, 2026-07-16) · precedence override: 0
- decision: a three-tier GitHub Actions architecture.
  - **Tier 1 — on push, every commit, < 3 min:** `lint.yml` (Ruff + tsc);
    `security.yml` pip-audit job (dependency CVE check); `pipeline-ci.yml` (Nextflow stub,
    unit tests now with coverage, lambda imports).
  - **Tier 2 — on PR / merge, ~10 min:** `security.yml` trivy-repo job (filesystem scan,
    SARIF -> Security tab); **`db-ci.yml` (schema apply, migration idempotency, seed data,
    immutability trigger tests)**; `docker.yml` (build, Trivy scan, push sha-tagged to GHCR);
    `coverage.yml` (PR coverage-delta comment, badge update on main).
  - **Tier 3 — scheduled / event-driven:** `maintenance.yml` (weekly full Trivy + license
    compliance, auto-issue on failure); `release.yml` (tag-triggered GitHub Release +
    versioned Docker image); Dependabot (weekly PRs for pip, npm, GitHub Actions, Docker).
- **explicitly required as machine-verified and blocking:** DB migration CI ("proves schema
  integrity is machine-verified, not trust-based") and immutability trigger tests ("validate
  the provenance/audit design in automation"). Both are Tier 2, gating PRs.
- **explicitly expected:** every PR gets **6+ status checks**.
- cost posture: $0 — all tooling free-tier (GitHub Actions 2,000 min/mo, Trivy, pip-audit,
  GHCR public, Dependabot built-in).
- clinical mapping: security scanning -> ISO 15189 §5.3 supply chain; license compliance
  protects an MIT codebase from GPL contamination; semver releases map to change-control docs.
- consequences requiring action: Dependabot PR noise (mitigated by grouped minor/patch);
  coverage badge needs one-time Gist setup; `maintenance.yml` needs `issues: write`;
  SARIF upload needs GitHub Advanced Security (free for public repos).

---

## Locked-decision roll-up (14 locked ADRs)

ADR-0001, ADR-0002, ADR-0003 (partial — engine superseded), ADR-0006, ADR-0007, ADR-0008,
ADR-0009, ADR-0010, ADR-0011, ADR-0012, ADR-0013, ADR-0014, ADR-0015, ADR-0016.

Not locked (superseded): ADR-0004 (partial — compute only), ADR-0005 (fully, as primary store).
