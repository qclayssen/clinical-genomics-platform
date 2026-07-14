# Changelog

Pipeline releases are semver-tagged. **Each version bump re-runs the GIAB validation
before tagging** — re-validation on change is a first-class rule, not an afterthought
(see `docs/VALIDATION.md` §7).

## [0.3.0] — 2026-07-10
### Added
- DeepVariant as a selectable caller (`--caller deepvariant`); caller concordance reporting.
- AWS CDK infra: S3 data lake (versioned, object-lock), Batch (Fargate/spot), scoped IAM, CloudWatch.
- AI reporting layer: QLoRA fine-tune + offline deterministic renderer with enforced review banner.
### Changed
- Provenance record now includes SHA-256 of every input file.

## [0.2.0] — 2026-06 (illustrative)
### Added
- `hap.py` validation module + `validation_pass` acceptance criterion.
- Postgres schema (insert-only) + ingestion.

## [0.1.0] — 2026-05 (illustrative)
### Added
- Core Nextflow pipeline: QC → align → mark-dup → HaplotypeCaller → MultiQC.
