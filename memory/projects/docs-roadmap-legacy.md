# Legacy plan: `docs/ROADMAP.md` (P0–P3)

## Status
Older roadmap, mostly superseded in practice by `.planning/ROADMAP.md`'s Phase 1–5 plan
(see `memory/projects/roadmap-v1-credibility-gaps.md`), but not deleted — its P1-1 item is
still open and its P2/P3 items remain legitimate future work.

## What's done
- **P0 (all three items) — done.** P0-1 (ADR-0011 supersedes ADR-0004, Batch→serverless),
  P0-2 (ADR-0012 supersedes ADR-0005, Postgres→DynamoDB primary), and P0-3 (the real GIAB
  HG002 chr20 validation run, replacing `_fill_` placeholders in `docs/VALIDATION.md` and the
  README table) are all marked complete.
- **P1-4 — done.** README's architecture section is a real Mermaid diagram (not ASCII), two
  demo GIFs exist, and the repo was made public after a security review.
- Most of P1 is therefore done; only **P1-1 remains open**.

## What's open
- **P1-1 — Pipeline finalization (the one open item in this roadmap).** Three sub-parts,
  meant to be done together:
  1. Real `versions.yml` collation — replace the current `collectFile`-based raw concat in
     `pipeline/main.nf` with a proper nf-core-idiom collation process
     (`CUSTOM_DUMPSOFTWAREVERSIONS`-style) that de-duplicates and emits a clean,
     MultiQC-ingestible `software_versions.yml`.
  2. A clean `nf-core lint` pass — reconcile `.nf-core.yml` ignores with reality and drive
     warnings to zero or a documented, justified ignore list.
  3. `nf-test` coverage — there are currently no `*.nf.test` files or `nf-test.config`; add
     tests for at least the QC, call, and validate modules plus a workflow-level test.
  - Depends on P0-3 (a real run surfaces version strings and lint edge-cases stub mode hides).
- **P1-2 — Nextflow migration doc**, depends on P1-1 landing (the doc should be complete,
  not partial); `docs/NEXTFLOW-MIGRATION.md` already exists and honestly flags the P1-1 items
  as open follow-ups.
- **P1-3 — Resume bullets** backed by the real measured F1 numbers; depends on P0-3 (done),
  so this is unblocked but still listed as not yet drafted.

## Future work (not yet started, not urgent)
- **P2-1 — MiXCR immune-repertoire (AIRR) branch.** Adds a second assay modality reusing the
  existing spine (provenance stamp, metadata model, Metabase dashboard, guardrailed AI
  summary) via a new `--assay {snv,airr}` selector and `pipeline/modules/repertoire/`. Depends
  on P0-3 and P1-1 landing first, so "reuse the spine" is demonstrated fact. Would be recorded
  as ADR-0013.
- **P3-1 — Spatial genomics.** Roadmap-ADR-only (status `Proposed`); explicitly **not** to be
  built, to preserve the project's single-person, tightly-scoped-portfolio positioning
  (ADR-0001).

## Explicitly out of scope for this roadmap
The **serverless infrastructure migration** (Lambda + Step Functions + DynamoDB) and the
**RAG reporter** (FAISS + Ollama) are owned by the Kiro spec
(`.kiro/specs/clinical-genomics-platform/tasks.md`) and are not tracked or re-planned here.
Specifically excluded: `metadata-stack.ts`/`orchestration-stack.ts`, the seven Lambda
handlers under `lambdas/` and the DynamoDB→Postgres sync, the RAG layer under
`ai-report/rag/`, and the property-based test suite / CDK guardrail updates / CI updates /
`docs/PRODUCTION-MIGRATION.md` that come with that migration. This roadmap only picks up the
docs/governance *consequences* those changes leave behind (P0-1, P0-2).

## Cross-reference
See `memory/glossary.md` for term definitions and `TASKS.md` at the repo root for current
task-level tracking (P1-1, P1-2, P1-3, P2-1 all appear there as open items).
