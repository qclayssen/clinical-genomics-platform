# ADR-0012 — DynamoDB as the primary metadata store (Postgres demoted to read-replica)

**Status:** Accepted · **Date:** 2026-07-15 · **Supersedes:** [ADR-0005](0005-insert-only-postgres.md)

## Context

ADR-0005 chose an **insert-only PostgreSQL** schema and *explicitly rejected DynamoDB* ("weaker
ad-hoc querying… no first-class Metabase story"). The serverless pivot ([ADR-0011](0011-serverless-lambda-stepfunctions.md))
changes the constraints: the Lambdas need a **serverless, always-free-tier, zero-idle-cost**
data store they can write to directly, with no VPC. Managed Postgres (RDS/Aurora) is not
free-tier and reintroduces a VPC. This ADR reconciles the pivot with the integrity model that
ADR-0005 was built to protect — and is honest that it **weakens** part of that model.

## Decision

Make **DynamoDB** the primary metadata store, and keep Postgres as a **read-replica for Metabase**:

- **Single-table `cgp-metadata`**: PK `run_id`, SK `record_type` ∈ {`RUN`, `QC_METRICS`,
  `PROVENANCE`, `AUDIT`, `CORRECTION`}; GSI `sample_id-created_at-index`; `PAY_PER_REQUEST`;
  **Point-in-Time Recovery on**; `RETAIN`.
- **Append-only** enforced by **IAM deny** of `dynamodb:DeleteItem` / `dynamodb:UpdateItem` on
  every Lambda role; a correction is a new `CORRECTION` item, never an in-place edit — the same
  "amend, never erase" rule as ADR-0005.
- **Postgres stays** (Option B): the metadata ingestor also feeds the local Postgres so the
  existing Metabase dashboard and `v_run_summary` keep working unchanged.

## Consequences

**Good**
- Serverless, always-free-tier, $0 idle; Lambdas write with no VPC; PITR gives recovery.
- Preserves the Metabase/dashboard investment (Postgres read-replica) and the correction-as-new-record semantics.

**Bad / accepted — THE KEY HONEST TRADEOFF**
- **The immutability guarantee gets weaker.** ADR-0005's Postgres `forbid_mutation()` trigger
  blocks UPDATE/DELETE at the database level — *unbypassable* without a schema change. DynamoDB
  has no equivalent; append-only here rests on **IAM policy**, which a table administrator or the
  account root can bypass (IAM is a perimeter control, not a data-level one). For a project whose
  selling point is ISO 15189-style tamper-evidence, this is a real regression, not a wash.
- **Compensating (detective) controls**, since the preventive control is weaker:
  1. **PITR** enabled — any mutation is recoverable/comparable to a prior point.
  2. **DynamoDB Streams → an append-only audit sink** (e.g. S3 object-lock) so any
     `MODIFY`/`REMOVE` event is recorded out-of-band and detectable.
  3. Writes restricted to the 7 scoped Lambda roles; no human/admin write path in normal operation.
- Ad-hoc querying is weaker than SQL — mitigated by the GSI and the Postgres read-replica for BI.

## Alternatives considered

- **Aurora Serverless v2** — keeps relational + DB-level triggers (preserving the *strong*
  immutability guarantee) and scales to zero-ish, but has a **minimum-ACU idle cost** (not truly
  always-free) and reintroduces a VPC. The closest "have both" option; noted as the production
  path if the free-tier constraint is relaxed.
- **Keep Postgres as primary (ADR-0005)** — rejected under the serverless/free-tier goal (needs
  RDS + VPC, not free-tier).
- **DynamoDB with Streams-verified writes only** — adopted in part (control #2 above) rather than
  as the whole design.
