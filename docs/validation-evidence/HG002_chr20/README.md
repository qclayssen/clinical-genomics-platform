# Validation evidence — HG002 chr20 run

This directory commits the two raw artifacts behind the headline validation numbers
(**SNV F1 = 0.9914, INDEL F1 = 0.9971**) reported in [`docs/VALIDATION.md`](../../VALIDATION.md)
§4 and the summary table in the main [`README.md`](../../../README.md). Previously these
lived only under the git-ignored `pipeline/results/` on the machine that ran them, so a
clone of this repo had no way to check the reported numbers against anything. This closes
that gap ([FIXES-TODO.md](../../FIXES-TODO.md) tracks the finding).

## What's here

| File | What it is |
|---|---|
| `HG002_chr20.happy.summary.csv` | The raw `hap.py` benchmark output — precision/recall/F1 per variant type, straight from the comparison engine, no post-processing. |
| `HG002_chr20.metrics.json` | The pipeline's provenance-stamped result record, built from the CSV above (and the MarkDuplicates metrics) by `pipeline/bin/build_metrics.py`. |

## Run details (from the files' own provenance fields)

- **Run ID:** `happy_mandelbrot`
- **Started:** 2026-07-15T21:23:06+10:00 (`started_at` in `metrics.json`)
- **Caller:** GATK HaplotypeCaller
- **Reference:** GRCh38.p14
- **Truth set:** GIAB v4.2.1, sample HG002/NA24385
- **Scope:** chr20:1,000,000-2,000,000 (1 Mb window — see the scope note in
  `docs/VALIDATION.md` §5), real (non-stub) GIAB reads, run through the actual Nextflow
  pipeline in Docker

## How to check the numbers yourself

1. Open `HG002_chr20.happy.summary.csv` and read the `SNP,PASS` and `INDEL,PASS` rows —
   `METRIC.F1_Score` is 0.991418 and 0.997067 respectively (rounded to 0.9914 / 0.9971 in
   the docs).
2. Open `HG002_chr20.metrics.json` and confirm `validation.snp.f1` and `validation.indel.f1`
   match, and that `validation_pass` is `true`.
3. The CSV's SHA-256 checksum, `ffbf5fd851969a03be7e48d8419dff41a0eff25767cae34beeab8abf93482ec7`,
   matches the value recorded under `provenance.input_checksums` in the JSON — that ties the
   two files in this directory together as the same run, independent of anything either file
   claims about itself.

## What this evidence does *not* prove

This is the two summary artifacts from a single run, not the full audit trail described in
[`docs/VALIDATION.md`](../../VALIDATION.md) §6: the reads, reference FASTA, and truth
VCF/BED used to produce this result are not checksummed here (a known, documented gap — see
§6), and the raw aligned BAM / called VCF are not committed (they're multi-GB and stay in
`pipeline/results/`, gitignored). What's committed here is exactly what a reviewer needs to
verify the *reported numbers themselves* are real and not aspirational — reproducing the run
end-to-end still requires [`docs/SOP-run-pipeline.md`](../../SOP-run-pipeline.md) or
[`docs/RUNBOOK.md`](../../RUNBOOK.md) and the real GIAB data via `scripts/fetch_testdata.sh`.
