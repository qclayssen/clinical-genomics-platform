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

## Phase 2 — Usage/value metrics (in progress)

Dispatched to a parallel agent — depends on Phase 1's `review_decisions` table, which is now
in place. Target: approval rate, review turnaround, F1 trend, sourced from `review_decisions`
+ existing `v_run_summary`.

## Phase 3 — Lightweight triage agent (in progress)

Dispatched to a background `cc-task` agent. Target: `ai-report/triage_agent.py` +
`docs/adr/0020-triage-agent.md`.

## Phase 4 — Enterprise data platform integration ADR (in progress)

Dispatched to a background `cc-task` agent (docs only). Target:
`docs/adr/0021-enterprise-data-platform-integration.md`.

## Phase 5 — GxP-flavored validation language (in progress)

Dispatched to a background `cc-task` agent (docs only). Target: edit `docs/VALIDATION.md`
with an IQ/OQ/PQ-style mapping section, no scope/certification overclaims.
