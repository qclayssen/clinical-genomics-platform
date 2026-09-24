# Validation evidence — HG002, chr20 1 Mb window, ~35× (depth comparison)

The artifacts behind the second row of [`docs/VALIDATION.md`](../../VALIDATION.md) §4: the
same chr20:1,000,000-2,000,000 window as the historical [`HG002_chr20/`](../HG002_chr20/) run,
downsampled from 269.7× to a measured 33.9×, so the effect of depth alone can be compared on
one region. **This is not the headline result** — see [`HG002_chr20_35x/`](../HG002_chr20_35x/).

- **SNV:** precision 0.9992, recall 0.9878, **F1 0.9934** · **INDEL F1:** 0.9969 ·
  `validation_pass: true`
- **QC layer:** `overall_status: fail` — `snp_recall` 0.9878 is below the 0.99 fail line in
  `pipeline/conf/qc_thresholds.yaml`, even though F1 passes the §3 acceptance criterion. See
  `docs/VALIDATION.md` §4 for why this disagreement is reported and not resolved here.
- **Run:** `sad_engelbart`, git commit `7ef24a70ac4c9a8cfad693c100352198d385738d`, GATK
  HaplotypeCaller `gatk4 4.5.0.0`, `-profile validation,docker` with
  `--intervals chr20:1000000-2000000 --truth_bed HG002_GRCh38_chr20_v4.2.1_window.bed`.

Files have the same meaning as in [`HG002_chr20_35x/`](../HG002_chr20_35x/README.md). The
`summary.csv`'s SHA-256 (`08b51c3be663f03331fa5c65752f58327100d9eb7ba8fa57c85021b1a8447404`)
matches `provenance.input_checksums` in `metrics.json`.
