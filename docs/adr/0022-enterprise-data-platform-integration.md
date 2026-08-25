# ADR-0022 — Enterprise data platform integration (design note)

**Status:** Proposed (design note, not implemented) · **Date:** 2026-08-01

## Context

This is a portfolio project scoped to run standalone (ADR-0017: local Nextflow, no AWS
account required to demo). It already has its own private `DataLakeStack` (`infra/lib/data-lake-stack.ts`
— a versioned, object-locked S3 bucket) and `MetadataStack` (`infra/lib/metadata-stack.ts` — a
single-table DynamoDB store for run records, QC metrics, provenance, and audit trail). Both
are scoped to this project alone; neither talks to anything outside it.

A job description this project is being tailored toward asks for "platform integration with
enterprise data platforms and existing scientific workflows" — i.e., not just having your own
data store, but plugging it into a larger organization's shared infrastructure (a corporate
data lake, a catalog, an ELN/LIMS). This ADR is a design note answering "how would this
platform's outputs reach that layer" — it is explicitly **not** implemented, and no
infrastructure code changes as part of it.

## Decision

Three integration points, each grounded in what already exists rather than inventing new
capability:

**1. Publish provenance-stamped results to a shared object store, not just the local lake.**
`pipeline/bin/build_metrics.py` already produces a fully provenance-stamped `metrics.json`
(git commit, tool/reference/truth-set versions, SHA-256 checksums — see CLAUDE.md). The
`DataLakeStack` bucket already emits EventBridge notifications on write
(`enableEventBridgeNotification()`). An enterprise integration would add a second EventBridge
rule that copies `metrics.json` (and, once it exists, `review_decisions` exports) to an
org-owned S3 prefix or cross-account bucket in a documented, versioned schema — the same
object, no transformation, so the checksum stays verifiable end-to-end. This is additive to
the existing bucket, not a replacement for it.

**2. Register in a data catalog conceptually, without committing to a specific product.**
The `MetadataStack`'s DynamoDB table already has the shape a catalog needs: `run_id` +
`record_type` as a composite key, a `sample_id` + `created_at` GSI for cohort queries. An
enterprise catalog integration (AWS Glue Data Catalog, or whatever the organization already
runs) would register the S3 prefix from point 1 as an external table pointing at that same
key structure, so scientists can query results through whatever BI/catalog tool the
organization standardizes on — not just this platform's own Metabase dashboard
(`dashboards/metabase/`). No specific catalog product is chosen here deliberately: the schema
is what needs to be stable, not the tool reading it.

**3. Let existing scientific workflows consume results without violating insert-only,
provenance-first design.** An ELN or LIMS would read, never write, this platform's data — the
integration is a one-way export, matching the insert-only invariant in `db/schema.sql`
(ADR-0005) and the `review_decisions` reviewer log (ADR-0019). Concretely: a scheduled or
event-driven export job reads `runs` / `qc_metrics` / `review_decisions` and writes to the
enterprise-visible copy from point 1; it never accepts writes back into this platform's own
Postgres or DynamoDB. This preserves the property that a correction here is always a new row,
never something an external system can silently overwrite.

## Consequences

**Good**
- Every claim in this ADR is anchored to a file that already exists (`data-lake-stack.ts`,
  `metadata-stack.ts`, `build_metrics.py`) — nothing here requires inventing a capability the
  platform doesn't have.
- The one-way, insert-only export model means an enterprise integration can never become a
  vector for silently rewriting results — it inherits the platform's own guarantees rather
  than needing new ones.
- Keeps the demo/CI story unchanged (ADR-0017): none of this requires an AWS account to run
  the existing test suite or the `-stub` pipeline profile.

**Bad / accepted limitations**
- Nothing here is implemented. This is a design note for interview/portfolio discussion, not
  working code — deploying it would require an actual target organization's catalog/ELN to
  integrate against, which doesn't exist in a solo portfolio project.
- Cross-account S3 replication and Glue Data Catalog registration both carry real IAM
  complexity (`infra/lib/iam-stack.ts` would need a new deny-delete-respecting cross-account
  role) that is sketched here, not designed in detail.

## Alternatives considered

- **Point the demo Metabase dashboard directly at an external catalog** — rejected as the
  starting design: couples this project's dashboard to infrastructure that doesn't exist yet;
  the export-based approach in point 1 works whether or not a catalog is present downstream.
- **Two-way sync (accept writes back from an ELN)** — rejected outright: breaks the
  insert-only, single-source-of-truth model that is the platform's core traceability
  guarantee (ADR-0005).
