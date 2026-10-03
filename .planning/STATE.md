---
gsd_state_version: '1.0'
status: planning
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 0
  completed_plans: 0
  percent: 80
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-21)

**Core value:** Every number the platform reports can be traced back to a provenance-stamped,
truth-set-validated run — and the repo never claims more than it has actually measured.
**Current focus:** Phase 5 — Reviewer Clickthrough (Phases 1–4 complete)

## Current Position

Phase: 3 of 5 (Full-Scope Validation Evidence)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-09-24 — Closed Phase 4 (DOC-01/02/03) ahead of Phase 3. Earlier: Closed out Phase 2 (Machine-Verified Integrity): per-role IAM deny
test (INTEG-01), ADR-0031 records the Streams audit sink as an accepted limitation (INTEG-02),
CLAUDE.md distinguishes IAM vs trigger controls (INTEG-03), db-ci.yml psql steps now fail on
SQL errors (CI-01).

Progress: [████████░░] 80%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: —
- Total execution time: —

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:** No plans executed yet.

## Accumulated Context

### Decisions

14 ADRs are LOCKED and must not be re-litigated — see PROJECT.md `<decisions status="LOCKED">`.
ADR-0004 (compute) and ADR-0005 (Postgres as primary) are superseded.

Open decisions blocking work: none.

Resolved:
- [Phase 2]: Build the DynamoDB Streams audit sink, or record it as an accepted limitation?
  **Answered by ADR-0031**: accepted limitation, residual risk stated.
- [Phase 1]: Where does real genomics compute run in the cloud? **Answered by ADR-0018** (affirms
  ADR-0017): local Nextflow is the sole real-compute path; cloud is orchestration/metadata only.
- [Phase 1]: Where does the healer Lambda's Ollama runtime execute? **Answered by ADR-0018**:
  nowhere in the cloud — `rule_based_classify()` is the only deployed path.
- [Phase 3]: Keep the locked full-chr20 scope, or narrow it? **Kept, by ADR-0037**: all of chr20
  at a downsampled ~35× (measured 33.7×); no native-depth full-chr20 run. SNV F1 0.9927.

### Pending Todos

None yet.

### Blockers/Concerns

- **[Phase 1] W1 — RESOLVED** — ADR-0018 records local Nextflow as the sole real-compute path
  (no cloud execution substrate, by design); do not plan any task that assumes one exists.
- **[Phase 1] W2 — RESOLVED** — `lambdas/healer/handler.py` no longer defaults `OLLAMA_URL`;
  `EscalateToHealer` remains a Step Functions `Pass` state (healer not deployed), and ADR-0018
  declares `rule_based_classify()` the only cloud-deployed path, enforced by
  `tests/test_healer.py` and the CDK no-localhost-endpoint test.
- **[Phase 2] W4 — RESOLVED** — `infra/test/stacks.test.ts` now asserts the DynamoDB mutation
  deny per writer role (mutation-checked). The Streams audit sink is not built; ADR-0031 records
  that as an accepted limitation.
- **[Phase 2] CI — RESOLVED** — the `|| true` / `|| echo` working-tree change described here is
  not present in the repo. The real gap was `psql -f` exiting 0 on SQL errors in `db-ci.yml`;
  fixed with `ON_ERROR_STOP=1`.
- **[Phase 3] W3 — RESOLVED** — `docs/VALIDATION.md` §4 now leads with all of chr20 at 33.7×
  (SNV F1 0.9927, precision 0.9903), evidence in `docs/validation-evidence/HG002_chr20_35x/`.
- **[Phase 3 → open] QC gate vs acceptance criterion** — `qc_thresholds.yaml` fails a run on SNV
  recall < 0.99 even when F1 ≥ 0.99 passes (the 1 Mb / 33.9× run does exactly that). Needs an
  ADR; tracked in `docs/FIXES-TODO.md`. Headline SNV precision (0.9903) also has a narrow margin.
- **[Phase 4] Doc drift — RESOLVED** — DOC-01/02/03 closed ahead of Phase 3 (its ordering
  dependency was on the measured numbers; none of the DOC items needed them). If Phase 3 changes
  the validated scope, re-check `CLAUDE.md` and `docs/VALIDATION.md` then.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Standards | Wire `ga4gh:SQ.` into run provenance (ADR-0010 next step) | v2 | 2026-07-21 |
| Validation | DeepVariant measured row; cohort validation | v2 | 2026-07-21 |
| Cloud | Build the HealthOmics path (only if Phase 1 picks option b) | v2 | 2026-07-21 |

## Session Continuity

Last session: 2026-07-21
Stopped at: Roadmap created from ingest intel; awaiting approval before planning Phase 1.
Resume file: None
