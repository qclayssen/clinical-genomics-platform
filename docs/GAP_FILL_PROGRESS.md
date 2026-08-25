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

## Phase 4 — Enterprise data platform integration ADR ✅ (2026-08-01)

**Shipped**
- `docs/adr/0022-enterprise-data-platform-integration.md` — a design note (explicitly
  "Proposed, not implemented," no infra code changed) covering three points, each anchored to
  a file that already exists rather than invented capability: (1) publishing the existing
  provenance-stamped `metrics.json` to a shared object store via the `DataLakeStack`'s
  existing EventBridge notifications, (2) registering the `MetadataStack`'s DynamoDB key shape
  in an external catalog without committing to a specific product, (3) one-way, read-only
  consumption by an external ELN/LIMS that preserves the insert-only invariant (ADR-0005) —
  never a two-way sync that could let an external system overwrite results.

**Why:** answers the JD's "Support platform integration with enterprise data platforms and
existing scientific workflows" line. Framed explicitly as a design note rather than shipped
infrastructure, since there is no real target organization's catalog to integrate against in
a solo portfolio project — the value here is demonstrating the integration *thinking*, not
overclaiming a deployed capability.

**Verification:** docs-only; reviewed against `infra/lib/data-lake-stack.ts` and
`infra/lib/metadata-stack.ts` for factual accuracy (bucket EventBridge notifications, table
key structure) before writing the ADR, so no claim in it is invented.

## Phase 5 — GxP-flavored validation language ✅ (2026-08-01)

Appended a new §8 to `docs/VALIDATION.md` mapping the platform's existing, already-implemented
validation mechanisms onto standard IQ/OQ/PQ vocabulary — Docker digest pinning and CDK
guardrail tests for IQ, the pipeline run + insert-only storage for OQ, the hap.py-vs-GIAB
benchmark for PQ — each claim cited to the actual file/table/script that satisfies it. The
section opens with an explicit disclaimer that this is vocabulary mapping for reviewer
readability, not a GxP certification or IQ/OQ/PQ sign-off claim, preserving the scope-honesty
framing required by CLAUDE.md and README.md.

**Why:** answers the JD's "Exposure to regulated/validated environments (GxP, IRB, FDA
risk/validation documentation) a plus" line, without overclaiming certification status the
project doesn't have.

**Verification:** docs-only; reviewed against CLAUDE.md's scope-honesty requirement —
disclaimer present, no capability overclaims, every IQ/OQ/PQ mapping cites a real file
(confirmed `infra/test/stacks.test.ts` exists before citing it).

---

All 5 phases complete. See individual PRs for review history:
Phase 1 (#52), Phase 2 (#53), Phase 3 (#54), Phase 4 (#55), Phase 5 (this PR).
