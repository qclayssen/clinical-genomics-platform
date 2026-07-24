# PR Review: #45 — fix(demo): chat intent routing + variant interpretation page

**Reviewed**: 2026-07-24
**Author**: qclayssen
**Branch**: fix/chat-intent-routing-and-variant-page → main
**Decision**: APPROVE with comments

## Summary
Bundles three commits: a real bug fix (plural intent routing in the chat assistant), a new Variant Interpretation demo page that surfaces the ReAct/deterministic ACMG agent, and lambda test coverage for `validation_checker`. Logic is correct, APIs used against `ai-report/agent/*` match their real signatures, and both new test files pass. Two non-blocking findings below, both around the new HTML-rendering helpers and `sys.path` hygiene.

## Findings

### CRITICAL
None

### HIGH
None

### MEDIUM
1. **`demo/pages/interpret.py` renders data-derived strings via `unsafe_allow_html` without escaping** — `_classification_badge`, `_evidence_chips`, `_render_trace_step` (the `content` field), and the `selected["summary"]` block all f-string-interpolate values sourced from the deterministic interpreter's trace/ClinVar/gnomAD lookups directly into HTML. Today the only input is the committed fixture VCF, so it's inert, but the moment this page accepts a user- or pipeline-supplied VCF (a natural next step for this feature), any of those strings becomes an HTML/script injection point. Worth routing through `st.markdown`'s default escaping or `html.escape()` before interpolation, or leaving a comment noting the trust boundary so it isn't missed later.

2. **`demo/pages/chat.py:430` — unconditional `sys.path.insert(0, ...)` on every report request** — `_generate_report()` inserts `ai_report_dir` into `sys.path` on every call with no membership check, unlike the guarded version added right next to it in `interpret.py` (`if str(_AI_REPORT) not in sys.path`). Since a Streamlit server process persists across reruns within a session, repeatedly asking the chat assistant to "generate a report" grows `sys.path` by one duplicate entry per request for the life of the process. Not a correctness bug, just unbounded (if slow) growth — an easy one-line fix to match the sibling file's pattern.

### LOW
None

## Validation Results

| Check | Result |
|---|---|
| Type check | Skipped (no type-check tooling configured for this repo) |
| Lint | Pass (`ruff check` on all 7 changed files) |
| Tests | Pass — 181 passed (`pytest`, excluding 5 pre-existing unrelated modules that fail to collect locally due to missing optional `hypothesis`/`yaml` deps, not touched by this PR) |
| Build | N/A (no build step for this repo) |

## Files Reviewed
- `conftest.py` — Modified (repo-root sys.path bootstrap for bare `pytest`)
- `demo/app.py` — Modified (added "Variant Interpretation" nav entry)
- `demo/intents.py` — Added (intent-routing rules extracted from `chat.py`, plural-matching fix)
- `demo/pages/chat.py` — Modified (delegates routing to `demo.intents`; see MEDIUM #2)
- `demo/pages/interpret.py` — Added (new Variant Interpretation page; see MEDIUM #1)
- `tests/test_demo_chat.py` — Added
- `tests/test_validation_checker.py` — Added
