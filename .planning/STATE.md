---
gsd_state_version: '1.0'
status: planning
progress:
  total_phases: 5
  completed_phases: 1
  total_plans: 0
  completed_plans: 0
  percent: 20
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-21)

**Core value:** Every number the platform reports can be traced back to a provenance-stamped,
truth-set-validated run — and the repo never claims more than it has actually measured.
**Current focus:** Phase 2 — Machine-Verified Integrity

## Current Position

Phase: 2 of 5 (Machine-Verified Integrity)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-09-22 — Closed out Phase 1 (Execution Substrate Decision): EXEC-01/02/03
satisfied by ADR-0017/ADR-0018, ADR-0002 annotated, CI guard added.

Progress: [██░░░░░░░░] 20%

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

Open decisions blocking work:
- [Phase 2]: Build the DynamoDB Streams audit sink, or record it as an accepted limitation?
- [Phase 3]: Keep the locked full-chr20 scope, or narrow it with a new ADR?

Resolved:
- [Phase 1]: Where does real genomics compute run in the cloud? **Answered by ADR-0018** (affirms
  ADR-0017): local Nextflow is the sole real-compute path; cloud is orchestration/metadata only.
- [Phase 1]: Where does the healer Lambda's Ollama runtime execute? **Answered by ADR-0018**:
  nowhere in the cloud — `rule_based_classify()` is the only deployed path.

### Pending Todos

None yet.

### Blockers/Concerns

- **[Phase 1] W1 — RESOLVED** — ADR-0018 records local Nextflow as the sole real-compute path
  (no cloud execution substrate, by design); do not plan any task that assumes one exists.
- **[Phase 1] W2 — RESOLVED** — `lambdas/healer/handler.py` no longer defaults `OLLAMA_URL`;
  `EscalateToHealer` remains a Step Functions `Pass` state (healer not deployed), and ADR-0018
  declares `rule_based_classify()` the only cloud-deployed path, enforced by
  `tests/test_healer.py` and the CDK no-localhost-endpoint test.
- **[Phase 2] W4** — `infra/test/stacks.test.ts:163` asserts DynamoDB deny actions exist somewhere
  in the IAM template, not that they are attached to every writer role. No Streams audit sink
  exists in `infra/lib/metadata-stack.ts`.
- **[Phase 2] CI** — an uncommitted working-tree change wraps CI steps in `|| true` / `|| echo`,
  making `db-ci.yml`, `lint.yml`, `pipeline-ci.yml`, `infra-ci.yml` and `security.yml` report
  green on failure. Contradicts ADR-0016. Deliberately left in place for now; do not plan around
  it as if committed.
- **[Phase 3] W3** — measured validation covers `chr20:1,000,000-2,000,000` at 255.8× depth.
  ADR-0001 locks full chr20. Requires Nextflow + Docker + the staged 11 GB BAM locally.
- **[Phase 4] Doc drift** — `CLAUDE.md` claims 9 ADRs (16 exist) and presents insert-only Postgres
  as the primary store's non-negotiable despite ADR-0012.

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
