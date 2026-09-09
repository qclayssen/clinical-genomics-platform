# ADR-0027 — REST API + React frontend for the existing variant interpreter

**Status:** Accepted · **Date:** 2026-09-09

## Context

ADR-0014 already built an agentic variant interpreter (ReAct loop + tool use over ClinVar/gnomAD/
gene annotations, with a deterministic fallback and ACMG/AMP combining rules,
`ai-report/agent/`). It was reachable two ways: the CLI (`ai-report/agent/interpret.py`, VCF-file
oriented) and a Streamlit demo page (`demo/pages/interpret.py`). Neither is callable from another
service, and neither demonstrates a REST API + modern SPA frontend — both are common integration
shapes for this kind of clinical tooling.

The first implementation attempt for this capability built a **second**, simpler agent package
from scratch (its own ACMG rules, its own tool stubs, its own sign-off table) before realizing
ADR-0014's agent already did all of this, better — with a real knowledge base, a ReAct loop, and
an existing insert-only sign-off log (`review_decisions`, ADR-0019). That duplicate was discarded
before merging; this ADR records the corrected decision.

## Decision

Add a REST endpoint and a React frontend that are **thin adapters over the existing agent**, not a
new one:

- `POST /agent/variant-review` (`api/routers/agent.py`) builds an `agent.react.Variant` from the
  request, runs it through `agent.deterministic.DeterministicInterpreter` (the zero-setup default —
  matching the policy `demo/pages/interpret.py` already established: no LLM, no network, no setup
  required to demo; `agent.react.ReActAgent` remains the upgrade path for a real LLM backend), and
  returns the full guardrailed report — classification, evidence codes, citations, and the
  complete Thought/Action/Observation trace, unmodified.
- Sign-off reuses the **existing** `POST /runs/{run_id}/review-decisions` endpoint and
  `review_decisions` table (ADR-0019) via `variant_key` (`chrom:pos:ref>alt`). No new table, no new
  sign-off endpoint — one audit trail for the whole platform, not two.
- `web/` is a small React + TypeScript + Vite app: a form for chrom/pos/ref/alt/gene/zygosity/
  run_id, a non-dismissible guardrail banner rendering the server's exact banner text, a
  step-by-step agent trace (not collapsed — the reasoning is the point), and an approve/reject
  sign-off control.

## Consequences

**Good**
- One variant-interpretation agent in the codebase, not two — avoids the confusing, lower-quality
  outcome of two competing implementations solving the same problem.
- Demonstrates the "assess what already exists before building" judgment this platform's ADR
  process is meant to produce, and the REST/React layer is itself new capability: programmatic and
  browser-based access where before there was only a CLI and a Streamlit page.
- Guardrail text is read from the API response, not hardcoded in the frontend, so the UI cannot
  silently drift from what the server enforces.

**Bad / accepted limitations**
- The React app duplicates some of what `demo/pages/interpret.py` already renders in Streamlit;
  the two aren't merged into one UI. Kept separate because they serve different purposes (Streamlit
  demo vs. a REST-backed SPA showing API/React skill) rather than out of oversight.
- `DeterministicInterpreter` is the only backend wired into the API route; `ReActAgent` (LLM-backed)
  is reachable from the CLI/demo but not yet from `POST /agent/variant-review` — left for a future
  ADR if a real LLM backend is worth wiring through the REST layer.

## Alternatives considered

- **Build a new, simpler agent for the REST/React layer** — rejected: this is what was actually
  attempted first, and discarded specifically because it duplicated ADR-0014's more capable,
  already-guardrailed implementation for no benefit.
- **A new `variant_assessments` table + bespoke sign-off endpoint** — rejected: `review_decisions`
  (ADR-0019) already does this, insert-only, for the whole platform; a second table would fragment
  the one audit trail into two.
- **Wire `ReActAgent` (LLM-backed) into the REST route by default** — rejected for now: it needs a
  configured LLM backend (Ollama/OpenAI/Anthropic) to add value over the deterministic path, which
  would break the zero-setup demo property this platform's API otherwise guarantees.
