# ADR-0019 — Capture reviewer sign-off as an insert-only decision log

**Status:** Accepted · **Date:** 2026-08-01

## Context

ADR-0008 guarantees every AI-drafted report carries the
**"AI-DRAFTED — REQUIRES CLINICIAN REVIEW"** banner and that a human is expected to review
it before any downstream use. But nothing in the platform previously recorded that a review
*happened*: who looked at a given interpretation, what they decided, and when. A guardrail
banner asserting "a human must review this" is not the same claim as "a human reviewed this,"
and only the second is auditable.

## Decision

Add a `review_decisions` table/store that records one row per reviewer decision:
`run_id`, `variant_key` (`chrom:pos:ref>alt`), `classification` (the AI output being judged),
`decision` (`approved` / `rejected`), `reviewer`, `comment`, `decided_at`.

- **Insert-only**, consistent with every other results table in this platform
  ([ADR-0005](0005-insert-only-postgres.md)): a changed mind is a new row, never an edit to
  the old one. The Postgres table (`db/schema.sql`) is covered by the existing
  `forbid_mutation()` trigger; the SQLite-backed demo store
  (`ai-report/agent/review_store.py`) simply exposes no update/delete method.
- **SQLite for the demo, Postgres schema for production** — the demo already runs with zero
  external infrastructure (`demo/data_loader.py`); requiring a live Postgres instance just to
  click Approve/Reject would break that property. The two schemas are kept in lockstep by
  hand for now (both fields and the insert-only invariant match).
- Wired into the existing "Variant Interpretation" demo page
  (`demo/pages/interpret.py`) rather than a new page: the report and its sign-off belong next
  to each other, and reviewing is the natural next action after reading a guardrailed report.
- A reviewer name is required to record a decision — an anonymous approval is not a
  meaningful audit trail entry.

## Consequences

**Good**
- Closes the loop ADR-0008 opened: the guardrail says review is required, this table proves
  it occurred, by whom, and when.
- Gives Phase 2 (usage/value metrics — approval rate, review turnaround) a concrete data
  source instead of a hypothetical one.
- Costs almost nothing to run: SQLite file, no new service, no new dependency.

**Bad / accepted limitations**
- The demo store and the Postgres table are not physically the same database; a production
  deployment would need a real sync path (or simply point the demo at Postgres directly) —
  out of scope for this portfolio-sized addition.
- No authentication on the reviewer name field; anyone using the demo can type any name. Fine
  for a demo, not fine for a real clinical deployment (would need SSO-backed identity).

## Alternatives considered

- **Log the decision only in `audit_log`** — rejected: `audit_log` is a generic free-text
  trail (`action`, `detail`); a decision needs structured, queryable fields
  (`decision`, `reviewer`) for the metrics work in Phase 2.
- **Store decisions as an UPDATE on the report row** — rejected outright: violates the
  insert-only design that is the whole point of this platform's traceability story.
