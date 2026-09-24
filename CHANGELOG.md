# Changelog

Pipeline releases are semver-tagged. **Each version bump re-runs the GIAB validation
before tagging** — re-validation on change is a first-class rule, not an afterthought
(see `docs/VALIDATION.md` §7).

## [Unreleased]
### Validation
- **Full-chr20 GIAB re-validation (Phase 3, ADR-0032).** All of chr20 at a measured 33.7×
  (downsampled from GIAB's 300× BAM, seed 42): SNV precision 0.9903, recall 0.9951,
  **F1 0.9927** (passes ≥ 0.99), INDEL F1 0.9862; stamped with git commit `7ef24a7`. Replaces
  the 1 Mb / 255.8× window as the headline result; evidence in
  `docs/validation-evidence/HG002_chr20_35x/`. The QC layer grades it `warn` (SNV precision
  and F1 below 0.995).

### Added
- `-profile validation` (`pipeline/conf/validation.config`) and
  `scripts/downsample_giab_bam.sh` for reproducible full-chr20 runs at representative depth.
- Provenance stamp now carries the raw FASTQ reads' SHA-256, the caller's self-reported
  version (`caller_version`), and the real git commit for local runs (was `local-dev`).

### Fixed
- Three failures only a real (non-stub) run could hit, found by the Phase 3 run:
  `qc_evaluate.py` was not executable, `QC_EVALUATE`'s container lacked PyYAML, and
  `samtools sort` in `BWAMEM2_ALIGN` could be OOM-killed at full-chromosome scale. None
  changes calling, filtering or the reference; the validation above ran with all three fixed.
- `qc_warnings` is now actually populated by a real pipeline run: `QC_EVALUATE.out.warnings`
  was a dangling channel in `pipeline/main.nf` (nothing downstream consumed it), so the table
  and its dashboard views were only ever populated by `db/seed_demo.sql`. `DB_INGEST` now
  joins the QC verdict onto `metrics.json`/the VCF and inserts one insert-only `qc_warnings`
  row per threshold breach (see `pipeline/bin/ingest_metrics.py`).
- Fixed the reason `QC_EVALUATE` never ran in the first place: `fastp.nf` emitted its JSON
  output as a bare `path`, not a `tuple(meta, path)`, so `QC_EVALUATE`'s `.join()` on
  `FASTP.out.json` always produced an empty channel and the process silently never fired
  (0 tasks, no error). No SNV calling, filtering, or reference logic changed, so this does
  not require re-running the hap.py-vs-GIAB benchmark (ADR-0003).
- `input_checksums` in the provenance stamp now also covers the reference FASTA, truth
  VCF and truth-set BED, not just the MarkDuplicates metrics and `hap.py` summary — a
  result is now cryptographically bound to what it was benchmarked against
  (`pipeline/modules/export/json_metrics.nf`, `pipeline/main.nf`; see `docs/VALIDATION.md`
  §6). No change to the caller, reference build, or filtering, so this does not require
  re-running the GIAB validation.

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
