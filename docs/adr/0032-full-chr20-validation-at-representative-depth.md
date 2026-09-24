# ADR-0032 — Validate full chr20 at a downsampled ~35× depth, not at the 300× source depth

**Status:** Accepted · **Date:** 2026-09-24
**Relates to:** [ADR-0001](0001-scope-giab-hg002-chr20.md) (locked scope: HG002, GRCh38 chr20 —
unchanged), [ADR-0003](0003-truth-set-validation.md) (benchmarking and the SNV F1 ≥ 0.99
criterion — unchanged), [ADR-0015](0015-happy-xcmp-engine-not-vcfeval.md) (xcmp engine —
unchanged), [ADR-0018](0018-execution-substrate-and-healer-llm-runtime.md) (local Nextflow is
the only real-compute path).

## Context

The first real validation run benchmarked a 1 Mb window (chr20:1,000,000-2,000,000) at the GIAB
source BAM's native depth (255.8× measured). Neither choice matches what the project claims:
ADR-0001 locks the scope to **all of chr20**, and a 255.8× result says little about the
30–40× depth a clinical WGS assay actually runs at — deep coverage hides caller weaknesses that
show up at realistic depth.

The only source of HG002 chr20 reads the pipeline has been run against is NIST's
`HG002.GRCh38.300x_chr20.bam` (12.1 GB). Real compute runs locally (ADR-0018): one 8-core
arm64 laptop with an 8 GB Docker VM, running amd64 Biocontainers under emulation. At native
depth, full chr20 is ~55 M read pairs; GATK HaplotypeCaller walks the chromosome
single-threaded, so a native-depth full-chr20 run is measured in days on this substrate, not
hours.

## Decision

1. The headline validation run covers **all of chr20** — no `--intervals` window, the full
   GIAB v4.2.1 chr20 high-confidence BED — at **~35× depth**, downsampled from the 300× source
   BAM by seeded read-name-hash subsampling (`scripts/downsample_giab_bam.sh`, seed 42), and
   is executed with `-profile validation`.
2. That single run satisfies both the full-scope requirement (VAL-01) and the representative-
   depth requirement (VAL-02). A separate full-chr20 run at native 300× depth is **not**
   performed: it adds no evidence about clinical-depth performance, and it cannot be run on
   the only real-compute substrate the project has.
3. A second, cheap run on the original 1 Mb window, downsampled with the same seed and
   target depth, is recorded beside the historical 255.8× window result, so the effect of
   depth alone can be read off one region.
4. The historical 1 Mb / 255.8× result stays in `docs/VALIDATION.md` as history. It no longer
   backs the headline claim.

## Consequences

**Good**
- The reported SNV F1 covers the locked ADR-0001 scope and a depth a reviewer recognises as
  clinically representative. No reported metric depends on the 255.8× source depth.
- The downsampling is seeded and scripted, so the exact read set is reproducible from the public
  BAM.

**Bad / accepted limitations**
- No native-depth full-chr20 figure exists. If one is ever needed, it requires cloud compute
  that ADR-0018 deliberately does not provide.
- Downsampling one very deep library is not the same as sequencing a fresh 35× library: it
  keeps that library's insert-size and error profile, and it does not model PCR-duplicate
  rates at a real 35× run.
- The single-sample, high-confidence-BED, xcmp and INDEL-not-gated limitations in
  `docs/VALIDATION.md` §5 all still apply.
