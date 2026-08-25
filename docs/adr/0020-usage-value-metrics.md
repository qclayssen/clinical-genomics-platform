# ADR-0020 — Usage/value metrics computed from the reviewer decision log

**Status:** Accepted · **Date:** 2026-08-01

## Context

ADR-0019 added `review_decisions`, an insert-only log of reviewer approve/reject sign-off on
AI-drafted interpretations. On its own that table is provenance, not insight: nobody could yet
answer "is the AI draft actually useful," "is it F1 holding up run over run," or "is the
review workflow being adopted at all." Those are exactly the kind of usage/performance/value
numbers a platform like this needs to demonstrate, and the data to compute most of them was
already sitting in `review_decisions` and the existing `v_run_summary` view — it just hadn't
been queried or documented.

## Decision

Add a small, fixed set of usage/value metrics, each backed by read-only SQL against existing
tables/views — no new mutation path, no new table beyond what ADR-0019 already introduced:

1. **AI-draft approval rate** — `approved / (approved + rejected)`, overall and by
   `classification`, from `review_decisions`.
2. **Review turnaround** — explicitly **not implemented** against the current schema.
   `review_decisions.decided_at` has no matching "draft produced at" timestamp to diff against;
   inventing a join against `runs.exported_at` would conflate pipeline turnaround with review
   turnaround and produce a misleading number. Documented instead as a schema gap: a
   `drafted_at` timestamp (new column or a sibling insert-only `ai_drafts` table) would make
   this derivable.
3. **SNP F1 trend over runs** — a straight `ORDER BY started_at` read of the existing
   `v_run_summary` view (`db/schema.sql`), plus a windowed variant flagging drops below the
   ADR-0003 acceptance threshold (F1 ≥ 0.99).
4. **AI-review adoption/coverage** — count of distinct `run_id`s with at least one reviewed
   decision versus total rows in `runs`, as a proxy for whether the human-in-the-loop workflow
   (ADR-0008) is actually being exercised, not just built.

All four are documented with runnable SQL in `docs/METRICS.md`. The Python-side equivalent
(`ai-report/agent/metrics.py::summarize_decisions`) is a pure function over
`list[ReviewDecision]` — no DB connection required — so the same approval-rate and
per-classification breakdown is available in the demo (SQLite) path and is unit-testable
without Postgres, mirroring how `review_store.py` itself stays dependency-light.

## Consequences

**Good**
- Turns the ADR-0019 decision log into an answer to "track usage, performance, and value
  delivered" using data the platform already writes — no new insert-only table, no schema
  churn.
- The turnaround gap is written down as a known limitation with a concrete fix, rather than
  quietly faked with a wrong join — keeps the provenance story honest.
- `summarize_decisions()` is pure and DB-free, so it's covered by fast unit tests
  (`tests/test_review_metrics.py`) and reusable from a future Streamlit metrics panel without
  pulling in SQLAlchemy/psycopg2.

**Bad / accepted limitations**
- Review turnaround is a documented gap, not a shipped metric — a real deployment would need
  the `drafted_at` field described above before that number exists.
- These queries are not yet wired into `dashboards/metabase/` as saved questions; today they
  live only as runnable SQL in `docs/METRICS.md`. Wiring them into Metabase is a natural
  follow-up, not done here to keep this change scoped to the metrics logic itself.
- `counts_by_classification` in the Python helper has no SQL-side pagination/limit — fine at
  portfolio scale, would need one at real volume.

## Alternatives considered

- **Approximate review turnaround via `decided_at - runs.exported_at`** — rejected: `runs`
  represents pipeline completion for an entire sample, not the moment a specific variant's AI
  draft was handed to a reviewer; the join would silently misattribute pipeline latency to
  review latency.
- **Compute metrics only in SQL, skip the Python helper** — rejected: the demo runs on SQLite
  with no Postgres available, and the existing `review_store.py` pattern already keeps
  demo-path logic dependency-free and unit-tested in pure Python.
- **Add a materialized view / rollup table for approval rate** — rejected as premature: at
  portfolio scale (single-digit runs, tens of decisions) a direct aggregate query is instant;
  a rollup table would be new state to keep insert-only-consistent for no measurable benefit.
