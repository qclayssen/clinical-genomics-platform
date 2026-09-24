# Validation evidence — HG002, all of chr20, ~35× (headline run)

The artifacts behind the headline row of [`docs/VALIDATION.md`](../../VALIDATION.md) §4:
**SNV F1 = 0.9927** (precision 0.9903, recall 0.9951) over all of chr20 at a measured
33.7× mean depth — the locked scope of [ADR-0001](../../adr/0001-scope-giab-hg002-chr20.md)
at the depth set by [ADR-0032](../../adr/0032-full-chr20-validation-at-representative-depth.md).

## What's here

| File | What it is |
|---|---|
| `HG002_chr20_35x.happy.summary.csv` | Raw `hap.py` output (xcmp engine), per variant type, no post-processing. |
| `HG002_chr20_35x.metrics.json` | The provenance-stamped result record `build_metrics.py` built from it. |
| `HG002_chr20_35x.qc_warnings.json` | The `QC_EVALUATE` verdict against `pipeline/conf/qc_thresholds.yaml` — `overall_status: warn` (SNV precision and F1 below the 0.995 warn line, no failures). |
| `HG002_chr20_35x.downsample.tsv` | How the input reads were made: source BAM, source depth (281.67×), seed (42), fraction (0.1243). |
| `software_versions.yml` | Every process's self-reported tool version, collated by the pipeline. |

## Run details (from the files' own provenance fields)

- **Run ID:** `crazy_venter`, started 2026-09-24T18:07:38+10:00
- **Git commit:** `7ef24a70ac4c9a8cfad693c100352198d385738d` (clean tree)
- **Caller:** GATK HaplotypeCaller, `gatk4 4.5.0.0`
- **Reference:** GRCh38.p14 chr20 · **Truth set:** GIAB v4.2.1, full chr20 high-confidence BED
- **Reads:** 2 × ~0.9 GB FASTQ, SHA-256 of each in `provenance.input_checksums`
- **Command:** `nextflow run main.nf -profile validation,docker`; `hap.py` ran as
  `hap.py <truth.vcf.gz> <query.vcf.gz> -f HG002_GRCh38_chr20_v4.2.1.bed -r GRCh38_chr20.fa --threads 4 --engine xcmp`
- **Wall time:** ~1 h 13 min on an 8-core arm64 laptop (amd64 images under emulation);
  HaplotypeCaller 45 min, bwa-mem2 11 min.

## How to check the numbers yourself

1. In `HG002_chr20_35x.happy.summary.csv`, the `SNP,PASS` row's `METRIC.F1_Score` is
   0.99266, `METRIC.Precision` 0.990252, `METRIC.Recall` 0.995079.
2. `HG002_chr20_35x.metrics.json` has the same values under `validation.snp`, and
   `validation_pass: true`.
3. `sha256sum HG002_chr20_35x.happy.summary.csv` gives
   `1c86d38c939bf553ad92440f24b15b86fe4dc3a24ad32bfa825c6bd4bb6f4759`, the value under
   `provenance.input_checksums` in the JSON — tying the two files together as one run.

## What this evidence does *not* prove

The BAM and VCF are not committed (multi-GB, in git-ignored `pipeline/results/`), so a
reviewer can check the reported numbers against the raw benchmark output, not re-derive the
benchmark itself. The source BAM the reads were downsampled from is identified by name, not
checksum. Container images are tag-pinned, not digest-pinned ([ADR-0009](../../adr/0009-docker-pinned-by-digest.md)).
See [`docs/VALIDATION.md`](../../VALIDATION.md) §5–§6 for the full list of limitations.
