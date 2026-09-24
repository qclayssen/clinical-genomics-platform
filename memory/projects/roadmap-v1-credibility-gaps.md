# Active plan: `.planning/ROADMAP.md` (v1 credibility gaps)

## Status
0 of 5 phases started as of writing. This is the **current active roadmap** for the project.

## Goal
The platform (M0–M8) is already built. This plan does not add features — it closes the
distance between what the repo *claims* and what it has *proven*, across five phases that
must run in order: 1 → 2 → 3 → 4 → 5.

## Why phase order matters (dependency chain)

- **Phase 1 — Execution Substrate Decision** runs first because it is the only genuinely
  open architectural question left (where does real genomics compute run: AWS Batch vs.
  HealthOmics vs. other). Every later document fix and any future cloud task would otherwise
  be planned against a capability that may not exist. Output is a new ADR plus alignment
  across `docs/SOP-run-pipeline.md`, `docs/usage.md`, `docs/MILESTONES.md` M4, and the
  ADR-0002/ADR-0009 references — not a build.

- **Phase 2 — Machine-Verified Integrity** depends on Phase 1. It makes the "integrity is
  machine-verified, not trust-based" claim actually true for the DynamoDB primary store
  (not just the Postgres replica), and makes the CI status checks genuinely blocking rather
  than printing warnings and passing. Concrete trigger: an uncommitted working-tree change
  wraps CI steps in `|| echo "non-blocking"` — this phase must either revert it or supersede
  ADR-0016 with a new ADR justifying non-blocking checks.

- **Phase 3 — Full-Scope Validation Evidence** depends on both Phase 1 (the execution path
  for the run must be settled before running it) and Phase 2 (re-validation is gated by the
  now-blocking CI checks). This produces the headline evidence: a full-chr20 hap.py run at
  representative (~30–40×) depth, since the current committed numbers were measured at an
  unrepresentative 255.8× depth. Needs Nextflow + Docker + the staged 11 GB GIAB BAM locally —
  the only phase in this milestone that cannot run in a dependency-free environment.

- **Phase 4 — Documentation Accuracy** depends on Phase 1 (substrate decision) and Phase 3
  (measured numbers), because writing these documents earlier would mean writing them twice
  and risks recording a claim that a later phase then contradicts. Fixes CLAUDE.md's ADR
  count and primary-store claims, the ADR index, and dangling cross-references (e.g. the
  ADR-0014 reference).

- **Phase 5 — Reviewer Clickthrough** depends on Phase 3 (measured numbers to surface) and
  Phase 4 (documents to link). Verifies the three-minute Streamlit demo clickthrough
  (home → explorer → variant interpretation → assistant) works end-to-end and displays the
  Phase 3 numbers alongside the scope statement and the mandatory AI-DRAFTED guardrail
  banners. Explicitly a clarity/honesty pass, not a redesign.

## Non-negotiables carried through every phase
- ADRs are append-only: a decision is a new next-numbered file, never an edit to an
  Accepted ADR's body.
- Never commit an unmeasured/placeholder number to `docs/VALIDATION.md` — if a real run
  can't be completed, the honest fallback is a new ADR narrowing the validated scope.
- The AI-DRAFTED guardrail banner and its provenance line must never be weakened to make
  the demo look better (ADR-0008, ADR-0014).

## Cross-reference
See `memory/glossary.md` for term definitions (Phase 1–5 names, ADR, hap.py, etc.) and
`TASKS.md` at the repo root for the current task-level tracking of this plan.
