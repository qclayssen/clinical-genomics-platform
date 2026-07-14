# Architecture Decision Records (ADRs)

## What is an ADR? (plain explanation)

An **Architecture Decision Record** is a short document capturing **one important decision**,
**why** it was made, and **what we gave up** by making it. Teams write them so that six
months later — or when a new person joins — nobody has to guess "why on earth did they use
X instead of Y?". The answer is written down, dated, and never edited (superseded, not
rewritten).

Each ADR follows the same tiny structure:

- **Status** — proposed / accepted / superseded
- **Context** — the situation and constraints that forced a choice
- **Decision** — what we chose
- **Consequences** — the good and the bad we now live with
- **Alternatives considered** — what else was on the table, and why we passed

> For a recruiter: ADRs are evidence of *engineering judgement*, not just coding. They show
> the candidate weighed trade-offs and can justify a design under review — exactly the
> conversation you'd have in a system-design interview.

## Index

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-scope-giab-hg002-chr20.md) | Scope to GIAB HG002, chr20, germline SNVs | Accepted |
| [0002](0002-nextflow-dsl2-pipeline.md) | Use Nextflow DSL2 (nf-core style) for the pipeline | Accepted |
| [0003](0003-truth-set-validation.md) | Validate by benchmarking against a truth set (hap.py) | Accepted |
| [0004](0004-aws-cdk-batch-fargate.md) | Deploy on AWS via CDK + Batch/Fargate | ~~Accepted~~ superseded by [0011](0011-serverless-lambda-stepfunctions.md) |
| [0005](0005-insert-only-postgres.md) | Store results in an insert-only PostgreSQL schema | ~~Accepted~~ superseded by [0012](0012-dynamodb-primary-store.md) |
| [0006](0006-metabase-dashboard.md) | Use Metabase for the operational dashboard | Accepted |
| [0007](0007-qlora-small-open-model.md) | Fine-tune a small open model with QLoRA (PyTorch) | Accepted |
| [0008](0008-guardrails-human-in-the-loop.md) | Enforce AI guardrails + human-in-the-loop in code | Accepted |
| [0009](0009-docker-pinned-by-digest.md) | Containerise every step, pin images by digest | Accepted |
| [0010](0010-ga4gh-standards-alignment.md) | Align with GA4GH standards; implement the refget/VRS digest primitive | Accepted |
| [0011](0011-serverless-lambda-stepfunctions.md) | Migrate compute Batch/Fargate → Lambda + Step Functions (free-tier) | Accepted (supersedes 0004) |
| [0012](0012-dynamodb-primary-store.md) | DynamoDB primary store; Postgres → Metabase read-replica | Accepted (supersedes 0005) |

## Conventions

- One decision per file, numbered sequentially, never renumbered.
- To change a past decision, add a **new** ADR that supersedes it and update the old one's
  status to `Superseded by ADR-XXXX`. We never silently edit history — the same principle
  as the insert-only database ([ADR-0005](0005-insert-only-postgres.md)).
