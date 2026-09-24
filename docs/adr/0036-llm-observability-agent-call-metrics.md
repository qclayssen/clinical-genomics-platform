# ADR-0036 — LLM observability for the variant agent: per-call accounting, dated cost estimates, insert-only `agent_call_metrics`

**Status:** Accepted · **Date:** 2026-09-24 · **Relates to:** [ADR-0005](0005-insert-only-postgres.md), [ADR-0008](0008-guardrails-human-in-the-loop.md), [ADR-0014](0014-agentic-variant-interpretation.md), [ADR-0028](0028-azure-bedrock-backends-and-fhir-intake.md)

## Context

The variant-interpretation agent (`ai-report/agent/`) can run against six LLM backends
(ADR-0014, ADR-0028). Its trace (`TraceStep`s, `AgentTrace`, `RunTrace`) already recorded
*what* the agent did, but not *what it cost*: `total_tokens` was a single number, calls were
not attributed to a backend/model, there was no latency per call, and no cost figure. Two
backends also zero-filled missing usage (`... if response.usage else 0`), so "0 tokens" could
mean either "none used" or "provider didn't say". Nothing was persisted, so the ops dashboard
could not compare backends over time.

Roadmap item AI-8 asks for per-step traces, token usage, cost estimate and latency.

## Decision

1. **Extend the existing trace, not a parallel one.** `InterpretationResult` and `AgentTrace`
   gain `llm_calls: list[LLMCallRecord]` (one per LLM call: backend, model id, prompt/completion
   tokens, latency ms, estimated cost, stop reason, tool-call count, index of the first
   `TraceStep` it produced, error flag) and an `llm_usage` summary. `RunTrace.summary` aggregates
   across variants. The accounting lives in `ai-report/agent/observability.py`.
2. **Never fabricate usage.** Backends now return `None` for token counts the provider did not
   report (OpenAI/Azure, Ollama, Bedrock paths; Anthropic always reports). Aggregates sum only
   reported calls and expose `n_calls_without_usage`. A failed call is recorded with its real
   latency and unknown tokens/cost. The deterministic backend's 0 tokens is truthful (no model).
3. **Cost is a labelled estimate.** A small `PRICE_TABLE` of list prices for the backends'
   default models, dated `PRICE_TABLE_AS_OF`, versioned as `PRICE_TABLE_VERSION` and stamped on
   every persisted row. Unknown model or missing usage → cost `None`, and any `None` makes the
   aggregate cost `None` (a partial sum would read as complete). Local backends (deterministic,
   Ollama) are 0.0 — no per-token charge, not a compute-cost estimate.
4. **Persist aggregates insert-only.** New table `agent_call_metrics` (one row per
   interpretation) in `db/schema.sql` and as forward migration
   `db/migrations/0002_agent_call_metrics.sql`, protected by the same `forbid_mutation()`
   row + TRUNCATE triggers as the other append-only tables and checked in `db-ci.yml`.
   `POST /agent/variant-review` writes the row through the repository; a write failure is logged
   (exception type only) and does not fail the interpretation. Token columns are NULL — not 0 —
   when no call reported usage.
5. **Dashboard.** Metabase card 11 in `dashboard_manifest.yaml`: mean latency, tokens and
   estimated cost per backend per day, with `calls_without_usage` shown alongside.
6. **Optional OpenTelemetry.** `AGENT_OTEL_ENABLED=1` plus an installed `opentelemetry-api`
   emits spans per agent run, per LLM call and per tool call. Otherwise every span helper is a
   no-op. OpenTelemetry is not added to any requirements file. Langfuse is not adopted.
7. **No PHI, no prompts.** Call records, span attributes (enforced by an allow-list) and table
   rows carry counts, ids and timings only: no prompt/completion text, no tool arguments, no
   variant coordinates. The reasoning trace itself keeps its content, because clinical review
   needs it. That content is not newly exported anywhere.

## Consequences

- Backend comparisons (latency/tokens/cost) become queryable. Cost figures are only as good
  as the dated table and must be re-checked against provider pricing before being quoted.
- `LLMResponse.usage` values may now be `None`; in-repo consumers were updated (`react.py`
  counts reported tokens only toward the token budget). An unreported-usage backend therefore
  cannot exhaust the token budget, and the iteration limit remains the backstop.
- `agent_call_metrics.run_pk` is nullable. The interpretation endpoint does not require the
  `run_id` to exist, and the row still records the `run_id` text.
- Only the REST path persists rows. The CLI (`interpret.py`) writes the accounting into its
  JSON trace/report but not to Postgres, and the Streamlit demo does neither.

## Alternatives considered

- **Langfuse / a hosted tracing SaaS.** More UI, but it's another service to run, and it wants
  prompts/completions by default, which conflicts with decision 7. OTel spans leave the choice
  of backend to the operator.
- **Estimating tokens with a tokenizer when the provider is silent.** Rejected: it would put
  guessed numbers next to measured ones in an audit-oriented table.
- **Storing per-call rows.** Deferred. Per-interpretation aggregates answer the dashboard
  question with far fewer rows, and per-call detail is already in the API response and trace JSON.
