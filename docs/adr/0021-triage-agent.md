# ADR-0021 — Post-run triage agent

**Status:** Accepted · **Date:** 2026-08-01

## Context

The platform can draft a guardrailed report (ADR-0008) and now records reviewer sign-off
(ADR-0019), but nothing decides, automatically and consistently, whether a completed run's
result is even worth drafting a report for. Today that call is implicit: whoever runs
`infer.py` by hand decides. A job description this project is being tailored toward calls out
"intelligent agents, automation scripts" distinct from a fine-tuned model — this closes that
gap with something small and inspectable rather than a new agent framework.

This is deliberately scoped narrower than two things that might sound similar:
- `lambdas/healer/handler.py` ([ADR-0018](0018-execution-substrate-and-healer-llm-runtime.md))
  diagnoses pipeline *execution* failures mid-run and recommends retry/quarantine actions on
  AWS Batch/Fargate.
- The ReAct variant-interpretation agent ([ADR-0014](0014-agentic-variant-interpretation.md))
  reasons about individual variants inside a VCF.

Neither of those decides what happens to a *finished run's* metrics.json — whether it's good
enough to draft a summary from, or needs to go back for re-validation first.

## Decision

Add `ai-report/triage_agent.py`: a plain script, not a new framework, structured as one
perceive → decide → act → log pass over a single `metrics.json`:

- **Perceive:** `load_metrics()` reads the file (same shape as `tests/fixtures/HG002_chr20.metrics.json`).
- **Decide:** `triage()` — a pure function, no side effects — checks `validation.snp.f1` against
  the platform's existing acceptance threshold (SNP F1 ≥ 0.99, per CLAUDE.md /
  `docs/VALIDATION.md`) and `validation_pass`. Below threshold, missing F1, or `validation_pass`
  false → `flagged_for_revalidation`. Otherwise → `drafted_and_queued`.
- **Act:** `run()` — when queued, calls the existing dependency-free `render_offline()` +
  `enforce_guardrails()` path from `ai-report/infer.py` (no new report-generation logic). When
  flagged, no report is drafted — re-validation is a human/pipeline decision, not something
  this script triggers automatically.
- **Log:** every decision is emitted as one structured JSON line
  (`{run_id, sample, action, snp_f1, reason}`), so it is trivially pipeable into a real log
  aggregator or, eventually, `db/schema.sql`'s `audit_log` table. Writing directly to Postgres
  from this script was deliberately left as a documented TODO rather than added — it would add
  a `psycopg2` dependency to a script whose whole point is staying as dependency-free as
  `infer.py --offline`.

## Consequences

**Good**
- Directly demonstrates an "automation script" distinct from the fine-tuned model or the
  interpretation agent — the JD lists these as separate things worth showing.
- Reuses existing, tested logic (`render_offline`, `enforce_guardrails`, the F1 threshold) —
  no new report format, no new guardrail path to keep in sync.
- Pure `triage()` function makes the decision trivially unit-testable without mocking a
  database or a model call (`tests/test_triage_agent.py`).

**Bad / accepted limitations**
- No real re-validation is triggered — `flagged_for_revalidation` is a label, not an action
  that re-runs the pipeline. Wiring that up would mean orchestrating Nextflow from Python,
  out of scope for this addition.
- The audit-log write is a TODO, not implemented — decisions are visible in stdout/logs but
  not yet queryable from Postgres alongside `runs`/`qc_metrics`.
- Threshold is hardcoded to match the platform-wide constant rather than read from
  `pipeline/bin/qc_thresholds.py`'s adaptive-threshold logic, which is scoped to per-run QC
  warnings (duplication rate, etc.), not the SNP F1 acceptance gate this script checks.

## Alternatives considered

- **Fold this into `infer.py` as a flag** — rejected: `infer.py` is a renderer, not a decision
  point; keeping triage as its own entry point keeps each script's job singular and testable.
- **Build on an agent framework (LangGraph, etc.) for the perceive/decide/act loop** —
  rejected: a three-branch decision over one JSON file doesn't need a graph runtime: the
  plain-function version is easier to read, test, and defend in an interview.
