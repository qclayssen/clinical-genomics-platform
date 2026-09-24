# Tasks

## To Do

- [ ] **Phase 3: Full-Scope Validation Evidence** - Run hap.py vs GIAB over the full chr20 scope at representative (~30-40x) depth, record honestly in docs/VALIDATION.md. Needs Docker + staged 11 GB BAM locally
- [ ] **Phase 5: Reviewer Clickthrough** - Verify the 3-minute Streamlit demo clickthrough works end-to-end and shows measured validation numbers + AI-DRAFTED guardrail banners
- [ ] **P1-1 (remainder)** - versions.yml collation (CUSTOM_DUMPSOFTWAREVERSIONS style); `nf-core lint` is blocked by tooling incompatibility with the hand-written module layout
- [ ] **P1-2: Nextflow migration doc** - Update docs/NEXTFLOW-MIGRATION.md with the nf-test work from #85
- [ ] **P1-3: Resume bullets** - Draft bullets backed by the real measured F1 numbers from docs/VALIDATION.md
- [ ] **P2-1: MiXCR immune-repertoire branch** - New `--assay {snv,airr}` path reusing the pipeline spine

## In Progress

## Done

- [x] **Phase 4: Documentation Accuracy** - [PR #87](https://github.com/qclayssen/clinical-genomics-platform/pull/87): stale ADR numbers in docs/ROADMAP.md fixed; ADR index verified (closed ahead of Phase 3)
- [x] **Phase 2: Machine-Verified Integrity** - [PR #86](https://github.com/qclayssen/clinical-genomics-platform/pull/86): per-role IAM deny test, ADR-0031 (Streams sink = accepted limitation), db-ci ON_ERROR_STOP
- [x] **P1-1 (nf-test)** - [PR #85](https://github.com/qclayssen/clinical-genomics-platform/pull/85): nf-test for QC/call/validate + workflow; fixed CWD-dependent samplesheet path bug
- [x] **Phase 1: Execution Substrate Decision** - [PR #84](https://github.com/qclayssen/clinical-genomics-platform/pull/84): annotated ADR-0002, CI cloud-executor guard, EXEC-01/02/03 satisfied
- [x] **P0-1 through P0-3** - ADR-0011/0012 supersessions, real GIAB HG002 chr20 validation numbers in VALIDATION.md
- [x] **P1-4** - README Mermaid architecture diagram, demo GIFs, repo made public after security review
