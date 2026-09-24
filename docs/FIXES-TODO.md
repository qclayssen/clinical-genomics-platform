# Fixes worth doing — consistency & control audit

**Status: the 2026-07-30 and 2026-09-10 audits below are closed as of 2026-09-15.** Kept as
a record of what was found and what was done about it, in the same append-only spirit as the
ADRs. Two genuine engineering gaps remain open — see the bottom section.

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

## Closed — 2026-09-10/2026-09-15 audit

| # | Item | Resolution |
|---|---|---|
| 8 | [P1] Provenance checksums covered only two derived outputs | **Fixed (#78).** `pipeline/modules/export/json_metrics.nf` now also checksums `params.reference`, `params.truth_vcf`, and `params.truth_bed`, threaded through `pipeline/main.nf`; `docs/VALIDATION.md` §6 updated. Raw FASTQ reads are still not checksummed — see the still-open item below. |
| 9 | [P1] `lambdas/validation_checker` synthesised metrics with no `simulated` marker | **Fixed (#77).** `_simulate_validation_metrics()` now returns an explicit `simulated: true` field threaded through the S3 payload and handler response, and the sampled range was changed from an always-passing `[0.9975, 0.9995]`/`[0.9965, 0.9990]` to a symmetric `[0.980, 1.000]` band around the 0.99 threshold, so `validation_pass` can actually be `false` on this path. |
| 10 | [P2] `qc_warnings` never written by the pipeline | **Fixed (#80).** `DB_INGEST` now joins `QC_EVALUATE.out.warnings` and inserts one insert-only row per threshold breach (`pipeline/bin/ingest_metrics.py`). While verifying this, also found and fixed the reason `QC_EVALUATE` never ran at all: `fastp.nf` emitted its JSON output as a bare `path` instead of `tuple(meta, path)`, so `QC_EVALUATE`'s `.join()` on `FASTP.out.json` always produced an empty channel (0 tasks, no error). The stub DAG task count moved from 9 to 10 (11 with `--db_ingest`) as a result — see `docs/END-TO-END.md`. |
| 11 | [P2] Two divergent copies of `enforce_guardrails()` | **Fixed (#81).** Consolidated into `ai-report/guardrails.py` — one canonical 8-pattern advice-phrase list (the union of the old 3- and 8-pattern lists, so neither call site lost coverage), with `enforce_guardrails()` (full report) and `enforce_safety_constraints()` (report fragment) as the two entry points. `ai-report/infer.py`, `ai-report/agent/react.py`, and `lambdas/report_generator/handler.py` all import it now. |
| 12 | [P2] Validation evidence not committed | **Fixed (#79).** The real HG002 chr20 run's `metrics.json` and `hap.py` `summary.csv` (checksum-verified against each other) are now committed under `docs/validation-evidence/HG002_chr20/`, linked from `docs/VALIDATION.md` §4/§6. |
| 13 | [P3] Immutability CI covered 4 of 6 protected tables; TRUNCATE not guarded | **Already fixed, doc was stale.** Both were closed back on 2026-09-10 in the same commit as item 0 above (`37c334c`, PR #74): `db/schema.sql` has a `FOR EACH STATEMENT BEFORE TRUNCATE` trigger on all six protected tables, and `db-ci.yml`'s immutability job exercises `run_provenance`/`review_decisions` and a `TRUNCATE runs CASCADE;` check. This list simply wasn't updated at the time — corrected 2026-09-15. |

---

## Open

- **[P1] The SNV F1 ≥ 0.99 gate is recorded, not enforced.** `validation_pass` is computed in
  `pipeline/bin/build_metrics.py` but no process fails on it and neither ingest path
  (`ingest_metrics.py`, `lambdas/metadata_ingestor`) recomputes or acts on it, so a run with
  F1 < 0.99 is still ingested and reported. VALIDATION.md §3 now states this; closing it
  means failing or quarantining the run before DB_INGEST/report.

- **[P1] The committed validation evidence is not tied to a commit.** It records
  `git_commit: local-dev` (`workflow.commitId` is empty for a local checkout) and
  `pipeline_version: 0.3.0`; its recall (0.9894) also trips the pipeline's own `snp_recall`
  fail threshold. Needs a re-run from a clean, tagged checkout with the current stamp.

- **[P1] Container identity is not in the provenance stamp.** All 12 module containers are
  now pinned by `@sha256` digest ([ADR-0009](adr/0009-docker-pinned-by-digest.md)), guarded by
  `tests/test_container_pinning.py`. `DB_INGEST` moved from a non-existent
  `biocontainers/psycopg2:2.9.9` image to the repo's own `ghcr.io/qclayssen/cgp-tools:1.0.0`.
  Still open: the provenance map in `pipeline/main.nf` records no container digest and no tool
  versions (those reach `pipeline_info/software_versions.yml` only).

- **[P1] Raw FASTQ reads are still not checksummed** (the other half of item 8 above).
  Only the reference and truth set were added to `input_checksums` in #78; the input reads
  themselves aren't yet, so a result still can't be fully tied back to its raw input data.
