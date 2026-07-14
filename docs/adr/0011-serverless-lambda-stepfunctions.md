# ADR-0011 — Migrate compute from AWS Batch/Fargate to serverless (Lambda + Step Functions)

**Status:** Accepted · **Date:** 2026-07-15 · **Supersedes:** [ADR-0004](0004-aws-cdk-batch-fargate.md) (compute choice only)

## Context

ADR-0004 chose AWS Batch on Fargate for compute. In practice that stack pulls in a VPC and a
**NAT gateway (~$32/mo, not free-tier)** and Fargate tasks that cost money whenever they run —
so the platform cannot be left deployed as a live, zero-cost demo. For a portfolio project the
demo must be **$0 at idle** and re-runnable on demand within the AWS **always-free tier**.
Separately, an event-driven serverless design is itself a skill worth demonstrating for the
AWS-native genomics roles targeted.

This supersedes only the **compute** decision of ADR-0004; the "infrastructure as code via CDK,
reviewed in CI, tagged with data classification" and the S3 data-lake decisions of ADR-0004 are
retained.

## Decision

Replace the Batch/Fargate `compute-stack` with an **`orchestration-stack`**:

- **AWS Step Functions** state machine (`maxConcurrency: 1`) driving **7 Lambdas**
  (ingestion-trigger → qc-orchestrator → variant-calling → validation-checker → export-handler →
  metadata-ingestor → report-generator), each with retry (2×, 5s, backoff 2.0).
- **EventBridge** rule on S3 `raw/*.fastq.gz` → `StartExecution`; **SQS DLQ** (14-day) for
  failed deliveries; **SNS** for alarm notifications.
- Everything sized to the always-free tier: Lambda (1M req/mo free), Step Functions
  (4,000 transitions/mo free; ~70 used per 10 runs), EventBridge/SQS/SNS free, DynamoDB on-demand.
- A **`> $1` billing alarm** as a cost backstop, and a CI check asserting the synthesized
  templates contain **zero** Batch/Fargate/NAT/RDS/Bedrock/SageMaker resources.

## Consequences

**Good**
- **$0 idle**, re-runnable on demand — the deploy can stay live as a portfolio demo.
- Event-driven and per-Lambda least-privilege (see the 7-role IamStack); no VPC/NAT to secure.
- Demonstrates serverless orchestration, not just batch job submission.

**Bad / accepted limitations — stated honestly**
- **Lambda (≤512 MB, ≤15 min, no GPU) cannot run real genomics tools** (BWA-MEM2 alignment,
  DeepVariant, hap.py) on real WGS data. The Lambda path is an **orchestration demonstration** —
  it drives the workflow and records provenance/metadata, while the actual heavy compute runs
  via the local Nextflow pipeline. This is a genuine gap versus a production system.
- The **production migration path is documented, not built**: real serverless genomics would use
  **AWS HealthOmics** (workflow + sequence store) rather than Lambda — captured for
  `docs/PRODUCTION-MIGRATION.md`.

## Alternatives considered

- **AWS HealthOmics** — the correct production answer for serverless genomics, but not
  free-tier and heavier to stand up than a portfolio warrants; cited as the production path.
- **Keep Batch/Fargate (ADR-0004)** — rejected: idle cost (NAT + Fargate) breaks the $0-demo goal.
- **Plain Fargate tasks without Batch** — still needs a VPC + NAT; same cost problem.
- **EC2 spot** — cheaper compute but not free-tier and not serverless; more to operate.
