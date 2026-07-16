# Changelog

Pipeline releases are semver-tagged. **Each version bump re-runs the GIAB validation
before tagging** — re-validation on change is a first-class rule, not an afterthought
(see `docs/VALIDATION.md` §7).

## [Unreleased]

## [1.0.0] — 2026-07-16
### Added
- First real (non-stub) GIAB validation run: real GRCh38 chr20 reference, real GIAB
  v4.2.1 truth set, real HG002 reads (chr20:1,000,000-2,000,000 window). Real measured
  result: SNV F1 0.9914, INDEL F1 0.9971 — see `docs/VALIDATION.md`.
- ADR-0015: switched `hap.py` from vcfeval to xcmp engine (pinned container lacks
  `rtg-tools`).
- Release packaging: `bump-my-version` config, GitHub Release workflow, Docker image
  publishing to ghcr.io.
### Fixed
- `haplotypecaller.nf`: removed a `samtools faidx` call the `gatk4` container can't run
  (no `samtools` binary); the `.fai` is already staged via the reference glob.
- `happy_benchmark.nf` / `parquet_export.nf`: corrected pinned container tags
  (`hap.py:0.3.15--py27h5c5a762_0` → `...py27hcb73b3d_0`, `pyarrow:15.0.0` → `4.0.1`)
  that didn't exist on quay.io.
- `multiqc.nf`: fixed declared output filenames to match what MultiQC actually produces
  when `--title` is set (`multiqc_report.html` / `multiqc_report_data`).

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
