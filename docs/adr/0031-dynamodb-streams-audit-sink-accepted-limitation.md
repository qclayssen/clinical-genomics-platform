# ADR-0031 — DynamoDB Streams audit sink: not built, recorded as an accepted limitation

**Status:** Accepted · **Date:** 2026-09-24 · **Amends:** [ADR-0012](0012-dynamodb-primary-store.md) §Consequences, compensating control #2

## Context

[ADR-0012](0012-dynamodb-primary-store.md) made DynamoDB (`cgp-metadata`) the primary metadata
store and said plainly that this **weakens** the immutability guarantee: append-only rests on an
IAM deny, which a table administrator or the account root can bypass, whereas the Postgres
replica's `forbid_mutation()` trigger is enforced inside the database. ADR-0012 listed three
compensating (detective) controls:

1. Point-in-Time Recovery (PITR) on the table.
2. **DynamoDB Streams → an append-only audit sink** (e.g. S3 Object Lock), so any `MODIFY` /
   `REMOVE` event is recorded out-of-band and detectable.
3. Writes restricted to the scoped Lambda roles; no human/admin write path in normal operation.

Checked against the code on 2026-09-24:

| Control | State | Evidence |
|---|---|---|
| 1. PITR | **Built** | `infra/lib/metadata-stack.ts` — `pointInTimeRecoveryEnabled: true`, `RETAIN` |
| 2. Streams → audit sink | **Not built** | No `stream` configured on the table; no consumer, no sink bucket |
| 3. Scoped writer roles + deny | **Built and asserted** | `infra/lib/iam-stack.ts`; `infra/test/stacks.test.ts` asserts the DynamoDB mutation deny is attached to *every* role that can write DynamoDB, not just present somewhere |

ADR-0012's "Alternatives considered" describes control #2 as "adopted in part". That wording
over-states the repo: nothing of it exists. This ADR corrects the record.

## Decision

**Do not build the Streams audit sink. Record its absence as an accepted, named limitation.**

The residual risk is stated explicitly below, and every tamper-evidence claim in the repo must
distinguish the primary store's IAM-based control from the replica's trigger-based control.

## Why not build it now

- **It would not change what a reviewer can verify offline.** The sink's value is detective and
  only exists on a deployed account with real traffic. This repo's validated artefacts run
  locally ([ADR-0017](0017-local-nextflow-sole-real-compute.md),
  [ADR-0018](0018-execution-substrate-and-healer-llm-runtime.md)).
- **Cost and surface.** A stream consumer Lambda, an Object Lock bucket with a retention
  policy, and their IAM roles add permanent infrastructure and a retention commitment
  (Object Lock in compliance mode cannot be shortened or deleted) to a free-tier demo account.
- **Honest scoping is the project's stated value.** Naming the gap is preferable to a half-built
  control that looks like tamper-evidence but has never observed a real mutation.

## Residual risk (accepted)

- A principal with table-admin rights, or the account root, can `UpdateItem` / `DeleteItem` on
  `cgp-metadata`. **Nothing in the repo would detect it at the time.** Detection is limited to
  after-the-fact comparison against a PITR restore (35-day window) and to divergence from the
  Postgres replica, which is only as current as its last sync.
- The strong, unbypassable-without-a-schema-change guarantee applies **only to the Postgres
  replica** (`db/schema.sql`), and is exercised by `db-ci.yml`'s immutability trigger tests.

## What would reverse this decision

Deploying the platform against real samples, or any claim of production tamper-evidence for
the primary store. At that point build control #2 (`StreamViewType.NEW_AND_OLD_IMAGES` → a
consumer that writes each `MODIFY`/`REMOVE` record to an Object Lock bucket), add a CDK
guardrail test asserting the stream and the bucket's Object Lock configuration, and supersede
this ADR.

## Consequences

**Good**
- The decision record matches the code; ADR-0012 no longer implies a control that does not exist.
- The one integrity guarantee that *is* machine-verified per role (the IAM deny) is now asserted
  per role, so removing it from a single writer fails CI.

**Bad / accepted**
- The primary store has preventive (IAM) and recovery (PITR) controls, but **no real-time
  detective control**. That is weaker than ADR-0005's original design and weaker than ADR-0012
  intended.
