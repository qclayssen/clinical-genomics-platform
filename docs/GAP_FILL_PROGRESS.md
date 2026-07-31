# CSL Behring gap-fill — progress log

Tracks the plan agreed to close gaps against the CSL Behring "Technology Enabled Science"
role (hands-on AI/ML + automation builder for R&D scientists, agentic dev tools, regulated
environment). Each entry: what shipped, why, verification done.

## Phase 1 — Scientist-facing review UI ✅ (2026-08-01)

**Shipped**
- `ai-report/agent/review_store.py` — insert-only `ReviewStore` (SQLite): records reviewer
  decisions (`run_id`, `variant_key`, `classification`, `decision`, `reviewer`, `comment`,
  `decided_at`). No update/delete method exists by design.
- `db/schema.sql` — mirrored `review_decisions` Postgres table, covered by the existing
  `forbid_mutation()` insert-only trigger.
- `demo/pages/interpret.py` — added a "Reviewer sign-off" section under the guardrailed
  report: reviewer name + comment form, Approve/Reject buttons, and a decision-history table
  per variant.
- `docs/adr/0019-reviewer-decision-log.md` — records the decision and alternatives considered.
- `tests/test_review_store.py` — 8 tests covering insert, list/filter, ordering, validation
  (rejects blank reviewer / invalid decision), and that no mutation method is exposed.

**Why:** ADR-0008 asserts a human must review every AI-drafted report, but the platform never
recorded that a review occurred. This directly answers the JD's "scientist-facing
applications" and "human-in-the-loop" language with something a reviewer can actually click
through, not just read about.

**Verification:** `pytest tests/test_review_store.py -q` → 8 passed. Full suite run
(`pytest tests/test_review_store.py tests/test_agent_smoke.py -q`) → 1 pre-existing unrelated
failure (`test_provenance_stamp_has_required_fields`, an agent-version string mismatch
predating this change, confirmed via `git diff HEAD -- tests/test_agent_smoke.py` showing no
local edits to that file).

---

## Phase 2 — Usage/value metrics ✅ (2026-08-01)

**Shipped**
- `docs/METRICS.md` — four usage/value metrics with runnable Postgres SQL, each sourced from
  data the platform already writes: AI-draft approval rate (overall and by `classification`,
  from `review_decisions`), SNP F1 trend over runs (via the existing `v_run_summary` view,
  including a windowed drop-below-threshold flag), and AI-review adoption/coverage rate
  (distinct reviewed `run_id`s vs. total `runs`). Review turnaround is documented as **not**
  cleanly derivable from the current schema — `review_decisions.decided_at` has no matching
  "draft produced at" timestamp — rather than faked via a misleading join against
  `runs.exported_at`; the doc specifies the `drafted_at` field that would make it derivable.
- `ai-report/agent/metrics.py` — `summarize_decisions()`, a pure, DB-free function over
  `list[ReviewDecision]` returning approval rate, counts by decision, and counts by
  classification. Mirrors the SQL in `docs/METRICS.md` for the SQLite/demo path.
- `docs/adr/0020-usage-value-metrics.md` — records the decision, including why review
  turnaround was left as a documented gap instead of an invented join.
- `docs/adr/README.md` — added the ADR-0019 and ADR-0020 index entries (0019 had shipped in
  Phase 1 but was never indexed).
- `tests/test_review_metrics.py` — 4 tests: empty-input edge case, overall approval rate
  through a real `ReviewStore(db_path=":memory:")`, per-classification breakdown, and an
  all-rejected classification.

**Why:** ADR-0019 gave the platform an insert-only record of reviewer decisions but no way to
answer "is the AI draft actually useful," "is accuracy holding up run over run," or "is the
review workflow being adopted." This turns that log into the JD's "track usage, performance,
and value delivered" line, using only data already captured — no new insert-only table, no
schema churn — while being explicit about what the current schema can't yet answer honestly.

**Verification:** `pytest tests/test_review_metrics.py -q` → 4 passed.

## Phase 3 — Lightweight triage agent ✅ (2026-08-01)

**Shipped**
- `ai-report/triage_agent.py` — plain perceive/decide/act/log script over a single
  `metrics.json`: `triage()` (pure function) checks SNP F1 against the platform's existing
  ≥0.99 acceptance threshold and `validation_pass`, returning `flagged_for_revalidation` or
  `drafted_and_queued`. `run()` drafts a guardrailed summary (reusing `infer.py`'s
  `render_offline()` + `enforce_guardrails()`) only when queued. Every decision logs as one
  structured JSON line; a Postgres `audit_log` write is documented as a deliberate TODO rather
  than implemented, to keep the script dependency-free.
- `docs/adr/0021-triage-agent.md` — records the decision and explicitly scopes this apart from
  the existing AWS healer (`lambdas/healer/handler.py`, pipeline-failure retries) and the
  ReAct variant-interpretation agent (per-variant reasoning) so it reads as a new capability,
  not a duplicate of what was already there.
- `tests/test_triage_agent.py` — 5 tests: passing metrics queue+draft, below-threshold and
  missing-F1 metrics flag without drafting, and `run()`'s draft/no-draft branching.

**Why:** answers the JD's "intelligent agents, automation scripts" line with something
distinct from the fine-tuned summarizer — a small, inspectable decision script, not a new
framework. (Note: this was originally dispatched to a background `cc-task` agent, which
stalled indefinitely on an unanswerable permission prompt — confirmed via
`claude agents --json --all` showing `"waitingFor": "permission prompt", "state": "blocked"`.
The stuck sessions were abandoned and this phase was completed directly instead.)

**Verification:** `pytest tests/test_triage_agent.py -q` → 5 passed.

## Phase 4 — Enterprise data platform integration ADR (in progress)

Being completed directly in-session after the background `cc-task` dispatch stalled (same
permission-prompt issue as Phase 3). Target:
`docs/adr/0022-enterprise-data-platform-integration.md` (next free ADR number).

## Phase 5 — GxP-flavored validation language (in progress)

Dispatched to a background `cc-task` agent (docs only). Target: edit `docs/VALIDATION.md`
with an IQ/OQ/PQ-style mapping section, no scope/certification overclaims.
