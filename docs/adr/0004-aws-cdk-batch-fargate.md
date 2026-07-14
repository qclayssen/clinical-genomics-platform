# ADR-0004 — Deploy on AWS via CDK + Batch/Fargate

**Status:** Superseded by [ADR-0011](0011-serverless-lambda-stepfunctions.md) (compute only; the CDK/IaC and S3 data-lake decisions stand) · **Date:** 2026-05-10

## Context

The target roles are AWS-native genomics platforms. The infrastructure must be
**reproducible**, **reviewable** (an accreditation reviewer should be able to read how it's
built), and scale from "one sample on a laptop" to "many samples in the cloud" without
rewriting the pipeline. Manual console clicking fails all three.

## Decision

Describe all infrastructure as code using **AWS CDK (TypeScript)**, split into four stacks:
**data lake (S3)**, **compute (Batch on Fargate)**, **IAM**, and **observability
(CloudWatch)**. The Nextflow `aws` profile targets the Batch queue; nothing about the
pipeline logic changes between local and cloud runs.

## Consequences

**Good**
- Infrastructure is versioned, diffable, and code-reviewed like any other code; `cdk synth`
  runs in CI ([.github/workflows/infra-ci.yml]).
- Fargate means no EC2 hosts to patch or account for in a security review; per-job isolation.
- Guardrail Jest tests encode accreditation-relevant invariants (bucket versioning, public-
  access block, deny-delete on data) so a regression fails CI.

**Bad / accepted limitations**
- Deploying requires a real AWS account and incurs cost; CI only runs `synth`, not `deploy`.
- Fargate is convenient but not the cheapest or fastest for heavy callers like DeepVariant —
  a GPU/EC2 compute environment would be a follow-up for production-scale work.

## Alternatives considered

- **Terraform** — equally valid IaC; CDK chosen because it lets infra be expressed in a real
  language with unit tests, and because the AWS-genomics target teams lean AWS-first.
- **AWS Genomics CLI / managed Batch templates** — faster to stand up but hide the very IAM
  and storage decisions this project wants to *show*.
- **Kubernetes (EKS)** — more portable but far heavier operationally than a solo portfolio
  warrants; Batch matches the bursty, job-shaped workload better.
- **EC2 + EBS by hand** — rejected: not reproducible, not reviewable.
