# Fixes worth doing — consistency & control audit

**Status: the 2026-07-30 audit below is closed. Re-audited 2026-09-10; every item is
resolved or superseded.** Kept as a record of what was found and what was done about it,
in the same append-only spirit as the ADRs. Open engineering gaps found in the newer audit
are listed at the bottom — those are the live ones.

Severity: [P1] fix first · [P2] worth fixing · [P3] nice-to-have.

---

## Closed — 2026-07-30 audit

| # | Item | Resolution |
|---|---|---|
| 0 | [P1] CI immutability check was non-blocking | **Fixed.** `.github/workflows/db-ci.yml` now `exit 1`s when any immutability trigger fails to fire. |
| 1 | [P1] Broken coverage badge in README | **Fixed 2026-09-10.** The badge hard-coded the literal placeholder `COVERAGE_GIST_ID` and 404'd for every visitor; it was removed, with the rationale and re-enable steps recorded in the README source comment. `.github/workflows/coverage.yml` now skips badge publishing with a notice instead of failing the run when `GIST_TOKEN`/`COVERAGE_GIST_ID` are unset. |
| 2 | [P1] Validation F1 numbers conflatable with test fixtures | **Fixed 2026-09-10.** `tests/fixtures/README.md` now leads with an explicit table separating the measured run (SNV F1 0.9914 / INDEL 0.9971, `docs/VALIDATION.md` §4) from the synthetic fixture values (0.9978 / 0.9920). The fixture files themselves were left untouched — `csv.DictReader` in `pipeline/bin/build_metrics.py` would misparse an added comment line. |
| 3 | [P2] ADR count stated three different ways | **Fixed.** Normalised across `docs/adr/README.md`, `README.md`, `CLAUDE.md`, `MILESTONES.md`, `FOR-RECRUITERS.md`. |
| 4 | [P2] Pipeline module count 11 vs 12 | **Fixed.** All primary docs say 12, matching `find pipeline/modules -name '*.nf'`. Only the frozen `.kiro/specs/` scaffold still says 11. |
| 5 | [P2] Single squashed commit vs a process-discipline pitch | **Superseded.** History is no longer flat — the repo now carries a full PR-per-change history. |
| 6 | [P3] Internal `.planning/` drift | **Accepted as-is.** `.planning/` is agent scaffolding, explicitly non-authoritative; the primary docs are the source of truth. |
| 7 | [P3] Dashboard screenshot placeholder | **Fixed.** The README Capability Walkthrough now carries real captures under `docs/assets/`. |

---

## Open — from the 2026-09-10 audit

These are genuine engineering gaps, not doc drift. Each is a claim the docs have now been
corrected to stop overstating, so nothing here is currently mis-documented — but the
underlying work is still worth doing.

- **[P1] Provenance checksums cover only two derived outputs.**
  `pipeline/modules/export/json_metrics.nf` passes `--inputs '${dup_metrics},${happy_summary}'`
  — both pipeline *outputs*. The reads, `params.reference`, `params.truth_vcf` and
  `params.truth_bed` are never checksummed, so a result cannot be tied back to the reference
  and truth set it was benchmarked against.

- **[P1] No images are digest-pinned, and container identity is not in the provenance stamp.**
  `git grep '@sha256:'` returns nothing; all 12 module containers are tag-pinned.
  [ADR-0009](adr/0009-docker-pinned-by-digest.md) treats digest pinning as the production
  target — it is not yet met. The provenance map in `pipeline/main.nf` records no container
  and no tool versions (those reach `pipeline_info/software_versions.yml` only).

- **[P1] `lambdas/validation_checker` synthesises metrics with `random.uniform`.**
  The docstring is honest, but the emitted payload carries no `simulated` marker, so a
  synthetic F1 is indistinguishable from a measured one downstream. The sampled range is also
  bounded above 0.99, making `validation_pass` unconditionally true on that path.

- **[P2] `qc_warnings` is never written by the pipeline.**
  `QC_EVALUATE.out.warnings` is a dangling channel in `pipeline/main.nf`; the table and its
  dashboard views are populated only by `db/seed_demo.sql`.

- **[P2] Two divergent copies of `enforce_guardrails()`.**
  `ai-report/infer.py` and `lambdas/report_generator/handler.py` scrub 3 patterns;
  `ai-report/agent/react.py` scrubs 8. Only the `infer.py` copy has tests.

- **[P2] Validation evidence is not committed.**
  The 0.9914/0.9971 figures are genuine, but the run's `metrics.json` and `hap.py`
  `summary.csv` live in untracked `pipeline/results/`, so someone cloning the repo cannot
  verify them. Committing the ~2 KB summary under a clearly-named path would close this.

- **[P3] Immutability CI covers 4 of the 6 protected tables.**
  `db-ci.yml` exercises `runs`, `qc_metrics`, `audit_log`, `qc_warnings` — not
  `run_provenance` or `review_decisions`. The schema protects all six.

- **[P3] Row-level triggers do not fire on `TRUNCATE`.**
  `forbid_mutation()` is `BEFORE UPDATE OR DELETE ... FOR EACH ROW`; a statement-level
  `BEFORE TRUNCATE` trigger would close the gap.
