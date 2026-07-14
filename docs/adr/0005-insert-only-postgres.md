# ADR-0005 — Store results in an insert-only PostgreSQL schema

**Status:** Accepted · **Date:** 2026-05-14

## Context

Results and their provenance must be **queryable** (for the dashboard) and **tamper-evident**
(for the accreditation/audit story). In a clinical setting a record is never erased — a
correction is a new, dated entry, and the original remains. The storage layer should make
the wrong thing (silent edits/deletes) hard or impossible, not merely discouraged.

## Decision

Use **PostgreSQL** with an **insert-only** design: tables `runs`, `qc_metrics`,
`run_provenance`, and `audit_log` accept inserts but **`UPDATE`/`DELETE` are blocked by
database triggers**. Corrections are new `runs` rows; every ingestion writes an `audit_log`
entry. Provenance (git commit, tool/reference versions, input SHA-256 checksums) is stored
alongside each run.

## Consequences

**Good**
- Tamper-evidence is enforced at the database level, not left to application discipline.
- The history of every sample is fully reconstructable — the core traceability requirement.
- Postgres is free, ubiquitous, and Metabase connects to it natively
  ([ADR-0006](0006-metabase-dashboard.md)).

**Bad / accepted limitations**
- "Fixing" bad data means appending corrected rows and filtering to the latest — slightly
  more query complexity than mutable rows.
- A DB superuser could still disable triggers; this models the control, it isn't a hardened
  security boundary.

## Alternatives considered

- **Mutable relational schema** — simplest, but throws away the tamper-evidence that is the
  whole reason to build this carefully.
- **DynamoDB** — serverless and scalable, but weaker ad-hoc querying for a BI dashboard and
  no first-class Metabase story; relational fits the reporting need better here.
- **Append-only event log only (no tables)** — pure but over-engineered for the query
  patterns; the trigger-guarded relational tables give both integrity and easy reporting.
