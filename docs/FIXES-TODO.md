# Fixes worth doing — consistency & control audit

Audit date: 2026-07-30. Scope: repo consistency + one CI control gap, not a full
code-correctness review. No open PRs or issues at audit time — these are self-initiated
cleanups. Severity: [P1] fix first · [P2] worth fixing · [P3] nice-to-have.

---

## [P1] 0. CI immutability check was non-blocking (FIXED in this branch)

`.github/workflows/db-ci.yml` tests that insert-only triggers block UPDATE/DELETE on the
audit tables, but on failure it only set `PASS=false` and printed a "(non-blocking)"
warning — the step still exited 0. A broken insert-only trigger (the secondary enforcement
layer for audit-trail integrity) therefore passed CI green. This is the regression the
repo's own `.planning/COMPLIANCE-AUDIT-REAL.md` flagged as a critical BLOCK on PR #48;
#48 ("Restore blocking CI checks") merged without actually restoring the block.

Fix applied: the `else` branch now prints an error and `exit 1`s, so the job fails when any
immutability trigger does not fire. Consider also making each individual check exit on first
failure rather than only aggregating.

---

## [P1] 1. Broken coverage badge in README

`README.md` hard-codes the literal placeholder `COVERAGE_GIST_ID` in the badge URL, so it
renders broken for every visitor. `.github/workflows/coverage.yml` already reads the real
value from `${{ vars.COVERAGE_GIST_ID }}`. Fix: create the gist, set the repo variable, and
substitute the real ID — or remove the badge. A visibly broken badge reads worse than none.

---

## [P1] 2. Validation F1 numbers can be conflated with test fixtures

Two different SNV F1 numbers live in the repo:
- Reported real run = 0.9914 SNV / 0.9971 INDEL (README, docs/VALIDATION.md, CHANGELOG) — consistent.
- Test fixtures = 0.9978 SNV / 0.9920 INDEL (tests/fixtures/sample.happy.summary.csv,
  tests/fixtures/HG002_chr20.metrics.json) — synthetic, but unlabeled.

The README cites "hap.py summary.csv" as the source of the headline numbers, which is
exactly the fixture filename — so a reviewer who diffs them discounts the traceability pitch.
Fix (cheap): add a header comment to each fixture — "Synthetic fixture for unit tests; NOT
the validation run reported in docs/VALIDATION.md" — and a note in tests/fixtures/README.md.

---

## [P2] 3. ADR count stated three different ways

Actual ADR files in docs/adr/ = 17. docs/adr/README.md, README.md, CLAUDE.md say 17 (correct);
docs/MILESTONES.md says 16; docs/FOR-RECRUITERS.md says 9 (worst — recruiter-facing).
Fix: normalize MILESTONES.md and FOR-RECRUITERS.md to 17.

---

## [P2] 4. Pipeline module count: 11 vs 12

Actual module .nf files = 12. Most docs say 12; .kiro/specs/.../design.md still says
"11 modules". Fix: grep for "11 module" and normalize to 12; reconcile the module list once.

---

## [P2] 5. Single squashed commit vs a process-discipline pitch

git history is flattened to ~one commit despite merged PRs to #50. For a project themed on
change-control and audit trails, an empty history is a conspicuous mismatch. Not fixable
retroactively; be ready to explain it, or add a short note acknowledging the consolidation.

---

## [P3] 6. Internal .planning/ drift

.planning/* still says "16 ADRs" / "~281 tests" / "9 ADRs". Not recruiter-facing but public.
Either finish the "Documentation Accuracy" phase or mark .planning/ as non-authoritative.

---

## [P3] 7. Dashboard screenshot placeholder

README has a "Screenshot pending" block. Capture the Metabase dashboard to docs/assets/ or
drop the section until it exists.

---

## Suggested landing order

1. This PR: item 0 (CI exit 1).
2. Next PR: items 1-4 (badge, fixture labels, ADR count, module count) — cheap and visible.
3. Items 5-7 as product decisions / when Documentation Accuracy is picked up.
