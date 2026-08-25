# Usage & value metrics

Answers "track usage, performance, and value delivered" with a small set of metrics computed
from data the platform already writes: `review_decisions` (ADR-0019, reviewer sign-off on
AI-drafted interpretations) and the existing `v_run_summary` view (`db/schema.sql`).

Every query here is read-only SQL against the insert-only tables — no new tables, no new
mutation path. `ai-report/agent/metrics.py` provides the equivalent computation in Python for
the in-memory / demo (SQLite) case, so the same numbers are available without standing up
Postgres.

## 1. AI-draft approval rate

The fraction of reviewed AI-drafted interpretations a clinician approved, overall and broken
down by classification. This is the headline "is the AI actually useful" number — a low rate
means the model is drafting things reviewers routinely discard.

```sql
-- Overall approval rate
SELECT
    COUNT(*) FILTER (WHERE decision = 'approved')                       AS approved,
    COUNT(*) FILTER (WHERE decision = 'rejected')                       AS rejected,
    ROUND(
        COUNT(*) FILTER (WHERE decision = 'approved')::numeric
        / NULLIF(COUNT(*), 0),
        4
    ) AS approval_rate
FROM review_decisions;

-- Approval rate by classification (e.g. Pathogenic, Likely Pathogenic, VUS, ...)
SELECT
    classification,
    COUNT(*) FILTER (WHERE decision = 'approved')                       AS approved,
    COUNT(*) FILTER (WHERE decision = 'rejected')                       AS rejected,
    ROUND(
        COUNT(*) FILTER (WHERE decision = 'approved')::numeric
        / NULLIF(COUNT(*), 0),
        4
    ) AS approval_rate
FROM review_decisions
GROUP BY classification
ORDER BY classification;
```

## 2. Review turnaround

**Not cleanly derivable from the current schema.** `review_decisions.decided_at` records when
a reviewer acted, but the platform does not currently persist *when the AI draft was produced
and handed to the reviewer* — `ai-report/infer.py` writes the drafted report to disk (or
renders it in the demo) without a timestamped, insert-only record of that event. Diffing
`decided_at` against `runs.exported_at` would conflate pipeline turnaround with review
turnaround and silently overstate or understate the real gap, so we don't fake that join here.

To make this derivable, add a `drafted_at TIMESTAMPTZ NOT NULL DEFAULT now()` column (or a
sibling insert-only `ai_drafts` table keyed by `run_id` + `variant_key`, mirroring
`review_decisions`) written at the moment `enforce_guardrails()` successfully produces a draft.
Once that exists, review turnaround is:

```sql
-- Once ai_drafts(run_id, variant_key, drafted_at) exists:
SELECT
    d.run_id,
    d.variant_key,
    rd.decided_at - d.drafted_at AS review_turnaround
FROM ai_drafts d
JOIN review_decisions rd
    ON rd.run_id = d.run_id AND rd.variant_key = d.variant_key
ORDER BY rd.decided_at DESC;
```

This is intentionally left as a documented gap rather than an invented join against
`runs.exported_at` — see ADR-0020.

## 3. SNP F1 trend over runs

Uses the existing `v_run_summary` view (already joins `runs` + `qc_metrics`). Tracks whether
accuracy against the GIAB truth set (ADR-0003) is holding steady, improving, or regressing as
pipeline/tool/reference versions change.

```sql
SELECT run_id, pipeline_version, caller, started_at, snp_f1, validation_pass
FROM v_run_summary
ORDER BY started_at ASC;
```

A simple regression flag (has the most recent run's F1 dropped below the ADR-0003 acceptance
threshold, 0.99, or below the prior run):

```sql
SELECT
    run_id,
    started_at,
    snp_f1,
    LAG(snp_f1) OVER (ORDER BY started_at) AS prev_snp_f1,
    snp_f1 < 0.99 AS below_acceptance_threshold
FROM v_run_summary
ORDER BY started_at ASC;
```

## 4. AI-review adoption / coverage rate

How many runs actually had at least one AI-drafted interpretation reviewed, versus the total
number of runs — a proxy for whether the human-in-the-loop workflow (ADR-0008) is being used
in practice, not just built.

```sql
SELECT
    (SELECT COUNT(DISTINCT run_id) FROM review_decisions) AS runs_with_reviewed_ai_drafts,
    (SELECT COUNT(*) FROM runs)                            AS total_runs,
    ROUND(
        (SELECT COUNT(DISTINCT run_id) FROM review_decisions)::numeric
        / NULLIF((SELECT COUNT(*) FROM runs), 0),
        4
    ) AS adoption_rate;
```

## Scope note

These are portfolio-scale metrics meant to demonstrate the *pattern* of tracking usage and
value from provenance-carrying, insert-only data — not a production analytics pipeline. In a
real deployment these queries would back a Metabase dashboard (`dashboards/metabase/`,
ADR-0006) alongside the existing QC dashboard, rather than being run ad hoc.
