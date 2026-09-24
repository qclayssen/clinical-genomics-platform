# Analytical Validation Report

**Assay:** Germline single-nucleotide variant (SNV) calling, whole-genome sequencing
**Scope of this validation:** GRCh38, **all of chromosome 20**, at a measured **33.7× mean
depth** — the locked scope of [ADR-0001](adr/0001-scope-giab-hg002-chr20.md), at the
representative depth set by [ADR-0037](adr/0037-full-chr20-validation-at-representative-depth.md)
**Reference material:** GIAB HG002 / NA24385 (Ashkenazi son), NIST benchmark v4.2.1
**Comparator:** `hap.py` (xcmp engine — see [ADR-0015](adr/0015-happy-xcmp-engine-not-vcfeval.md)) against the v4.2.1 high-confidence VCF + BED

> This is a portfolio validation demonstrating *methodology*. It is not a clinical
> accreditation record. Framed after the structure of an ISO 15189 analytical
> validation so the intent is legible to reviewers.

## 1. Purpose

Establish the analytical performance (precision, recall, F1) of the pipeline's SNV
calls against a gold-standard truth set, and define the acceptance criterion used by
downstream automation.

## 2. Method

1. **Input reads.** NIST's `HG002.GRCh38.300x_chr20.bam` (12.1 GB, public/CC0) is
   downsampled to ~35× by seeded read-name-hash subsampling and written back to paired
   FASTQs with [`scripts/downsample_giab_bam.sh`](../scripts/downsample_giab_bam.sh)
   (seed 42; both mates of a pair are kept or dropped together, so the read set is
   reproducible from the public BAM). The fraction is computed against the source's own
   measured depth and recorded in each run's `*.downsample.tsv`.
2. Reads processed through the standard pipeline (`fastp` → `bwa-mem2` → MarkDuplicates
   → HaplotypeCaller) with `-profile validation,docker`
   ([`pipeline/conf/validation.config`](../pipeline/conf/validation.config)).
3. Output VCF compared to the GIAB truth VCF, restricted to the high-confidence BED — the
   full chr20 BED for the headline run, no `--intervals` window.
4. Metrics parsed from `hap.py summary.csv` into `metrics.json` (see `build_metrics.py`).
5. Mean depth is measured on the MarkDuplicates BAM (`samtools depth -a -G 0xD04`, every
   position in the region, zero-depth gaps included), not taken from the downsampling target.

## 3. Acceptance criterion

- **SNV F1 ≥ 0.99** within the high-confidence regions.
- Recorded per run as `validation_pass` (computed in `pipeline/bin/build_metrics.py`).
- **Not yet enforced.** Nothing in the pipeline, DB or dashboard blocks, fails, or withholds
  a run with `validation_pass: false` — it is a recorded flag that a reviewer has to check.
  Enforcement is an open item in [FIXES-TODO](FIXES-TODO.md).

## 4. Results

All three rows are real, non-stub runs of the Nextflow pipeline in Docker on real GIAB
HG002 reads, the real GRCh38 chr20 reference and the real GIAB v4.2.1 truth VCF/BED. The
**headline** row is the first; the other two are the same 1 Mb window at two depths, so the
effect of depth alone can be read off one region.

| Run | Region | Mean depth | Truth SNVs | SNV precision | SNV recall | SNV F1 | INDEL F1 | Ti/Tv¹ | `validation_pass` |
|---|---|---|---|---|---|---|---|---|---|
| **Headline** — 2026-09-24 | **all of chr20** | **33.7×** | 71,333 | 0.9903 | 0.9951 | **0.9927** | 0.9862 | 1.87 | ✅ true |
| Window, downsampled — 2026-09-24 | chr20:1,000,000-2,000,000 | 33.9× | 1,226 | 0.9992 | 0.9878 | 0.9934 | 0.9969 | 2.11 | ✅ true |
| Window, source depth (historical) — 2026-07-15 | chr20:1,000,000-2,000,000 | 255.8× | 1,226 | 0.9934 | 0.9894 | 0.9914 | 0.9971 | 2.07 | ✅ true |
| DeepVariant | — | — | — | _not yet run_ | _not yet run_ | _not yet run_ | _not yet run_ | — | — |

¹ Query Ti/Tv over *all* calls, including calls outside the high-confidence BED; not a
benchmarked metric.

**About the historical row.** It passes §3 but should not carry weight on its own: its
recall (0.9894) is below the QC layer's `snp_recall` fail line; with 1,226 truth SNVs
(13 FN, 8 FP) the 95% Wilson interval for its recall is roughly 0.982–0.994, so the margin
is within sampling noise; and its `metrics.json` predates the current stamp
(`git_commit: local-dev`, `pipeline_version: 0.3.0`, checksums of the two derived artifacts
only). The Phase 3 runs above were made from a clean checkout with the complete stamp (§6)
to replace it as evidence.

**Headline result.** Over all of chr20 at 33.7×, SNV F1 = 0.9927 meets the ≥ 0.99
acceptance criterion (§3): 70,982 of 71,333 truth SNVs recovered (351 false negatives),
699 false positives. Genotype mismatches are a small share of the errors (61 of the 699
FPs are `FP.gt`, 32 are `FP.al`).

**What the full scope showed that the window didn't.** The 1 Mb window is an easy region:
its precision (0.9992) is not representative. Over the whole chromosome, precision drops to
0.9903 — within 0.0003 of the 0.99 line on its own — so the headline F1 has a narrow margin,
driven by false positives rather than missed calls. That is the main reason the window
result should not be read as the platform's performance.

**What depth changed on the same window.** Downsampling from 255.8× to 33.9× raised
precision (8 → 1 false positive) and cost a little recall (13 → 15 false negatives); F1 moved
from 0.9914 to 0.9934. At this size (1,226 truth SNVs) the difference is a handful of sites
and not meaningful on its own.

**QC layer verdict ([ADR-0013](adr/0013-qc-warnings-adaptive-thresholds-self-healing.md)).**
`QC_EVALUATE` grades each component metric against
[`pipeline/conf/qc_thresholds.yaml`](../pipeline/conf/qc_thresholds.yaml), which is stricter
than the §3 acceptance criterion (it warns below 0.995 and fails below 0.99 for SNV precision,
recall and F1 separately):

| Run | `overall_status` | Failures | Warnings |
|---|---|---|---|
| Headline, full chr20 | **warn** | — | `snp_precision` (0.9903), `snp_f1` (0.9927) |
| Window, 33.9× | **fail** | `snp_recall` (0.9878) | `snp_f1` (0.9934) |
| Window, 255.8× (historical) | _not evaluated_² | — | — |

² `QC_EVALUATE` had never completed on a real run before Phase 3: `qc_evaluate.py` was not
executable and its container lacked PyYAML, so every real run failed there. Its recall of
0.9894 would also fall below the `snp_recall` fail line. The two gates disagreeing — a run
can pass §3 and fail the QC layer — is an open question, not resolved here; neither
threshold has been changed.

The raw `hap.py` summary, the provenance-stamped `metrics.json`, the `QC_EVALUATE` verdict,
the downsampling record and the collated tool versions for each run are committed under
[`docs/validation-evidence/`](validation-evidence/) — see
[`HG002_chr20_35x/`](validation-evidence/HG002_chr20_35x/) (headline),
[`HG002_chr20_window_35x/`](validation-evidence/HG002_chr20_window_35x/) and
[`HG002_chr20/`](validation-evidence/HG002_chr20/) (historical). Each directory's
`metrics.json` records the SHA-256 of its own `summary.csv`, so the pair can be checked
against each other from a clone.

## 5. Known limitations

- **Depth is downsampled, not sequenced.** The ~35× read sets are subsampled from one very
  deep library, so they keep that library's insert-size and error profile and do not model a
  real 35× run's duplicate rate (0.25% here). See
  [ADR-0037](adr/0037-full-chr20-validation-at-representative-depth.md).
- **No native-depth full-chr20 run.** A 255.8×-depth run over all of chr20 is ~55 M read
  pairs and is not feasible on the project's only real-compute substrate
  ([ADR-0018](adr/0018-execution-substrate-and-healer-llm-runtime.md)); ADR-0037 records why
  it is not needed for the validation claim.
- **Narrow precision margin.** Headline SNV precision is 0.9903; a caller, filter or
  reference change could plausibly push it below 0.99 — re-validation on change (§7) is not
  a formality here.
- Comparison uses `hap.py`'s **xcmp** engine, not vcfeval — see
  [ADR-0015](adr/0015-happy-xcmp-engine-not-vcfeval.md) for why (the pinned container lacks
  `rtg-tools`, and the alternative image bundling it can't be pulled with modern Docker).
  xcmp's representation matching is less forgiving of complex/nearby variants, so it can
  make precision/recall slightly more conservative than vcfeval would.
- Low-complexity / segmental-duplication regions are excluded by the GIAB
  high-confidence BED and are therefore **out of scope** of this validation.
- INDEL performance reported for information; the acceptance criterion is SNV-only.
- Truth set is a single sample (HG002); this is not a cohort validation.
- DeepVariant has not yet been run for a real comparison row.

## 6. Provenance of this validation

Every Phase 3 result row is traceable to the pipeline git commit, the pipeline version, the
caller and its version, the reference build (`GRCh38.p14`) and the truth-set version
(`GIAB-v4.2.1`) — captured automatically into `metrics.json` by
`pipeline/bin/build_metrics.py` and stored in `run_provenance`. The headline run's stamp:

| Field | Value |
|---|---|
| `git_commit` | `7ef24a70ac4c9a8cfad693c100352198d385738d` (clean tree — no `-dirty` suffix) |
| `pipeline_version` | `1.0.0` |
| `caller` / `caller_version` | `gatk` / `gatk4 4.5.0.0` (reported by the HaplotypeCaller process itself) |
| `reference_build` | `GRCh38.p14` |
| `truth_version` | `GIAB-v4.2.1` |
| `run_id` / `started_at` | `crazy_venter` / `2026-09-24T18:07:38+10:00` |

`git_commit` is read from the checkout at launch (`git rev-parse HEAD`) when Nextflow has no
`workflow.commitId`, with a `-dirty` suffix if the tree has uncommitted changes — the
2026-07-15 historical run predates this and is stamped `local-dev`.

`input_checksums` covers the **raw FASTQ reads**, the MarkDuplicates metrics, the `hap.py`
summary, the reference FASTA (`params.reference`), the truth VCF (`params.truth_vcf`) and the
high-confidence BED (`params.truth_bed`) — SHA-256 over each file, streamed rather than
loaded whole into memory. `JSON_METRICS` (`pipeline/modules/export/json_metrics.nf`) takes
the reads, reference and truth set as explicit process inputs, so a result is
cryptographically bound to the exact inputs it was produced from and benchmarked against.
The source BAM the reads were downsampled from is not itself checksummed; its name, the
seed and the fraction are recorded in `*.downsample.tsv`.

**Known gap in this stamp (tracked in [FIXES-TODO.md](FIXES-TODO.md)):**

- **Container identity is not in the stamp.** Every module image is now pinned by
  `@sha256` digest ([ADR-0009](adr/0009-docker-pinned-by-digest.md)), but no digest reaches
  the provenance block. Only the *caller's* version is in the stamp; the other tools'
  versions are collated separately into `pipeline_info/software_versions.yml` (committed
  beside each run's evidence, but not part of the result record). `hap.py` also reports an
  empty version string there; the pinned image tag is `hap.py:0.3.15--py27hcb73b3d_0`.
  The Phase 3 runs predate the digest pins by a few hours and were launched by tag; every
  image they used was checked afterwards and its local digest matches the digest now pinned
  in `pipeline/modules/` exactly — so the evidence was produced by the pinned images, but
  that was verified by hand, not recorded by the run.

The run artifacts backing §4 are committed under
[`docs/validation-evidence/`](validation-evidence/), one directory per run, so the tables
above are independently checkable from a clone without re-running anything. The full run
directories they were copied from (BAM, VCF, logs) are not committed — they live under the
git-ignored `pipeline/results/` and are multi-GB. To reproduce a run end-to-end, stage the
reference and truth set with `scripts/fetch_testdata.sh`, download the source BAM, run
`scripts/downsample_giab_bam.sh`, then `nextflow run main.nf -profile validation,docker`
(see [`pipeline/conf/validation.config`](../pipeline/conf/validation.config) and
[RUNBOOK.md](RUNBOOK.md)).

## 7. Change control

Any change to reference, caller, or filtering re-triggers this validation before the
new pipeline version is tagged in `CHANGELOG.md`. Re-validation on change is the point.

## 8. Mapping to computer-system-validation (IQ/OQ/PQ) vocabulary

> This section maps existing validation practices onto standard GxP vocabulary for
> readability to reviewers familiar with that framework. It does not claim GxP
> certification, IQ/OQ/PQ sign-off, or regulatory validation status — see the portfolio
> scope note at the top of this document and in [CLAUDE.md](../CLAUDE.md), which remains
> the authoritative scope statement for this project.

Regulated computer-system validation typically breaks into Installation Qualification (IQ),
Operational Qualification (OQ), and Performance Qualification (PQ). Each already has a
concrete counterpart in this repository:

| GxP concept | What it verifies | Existing mechanism here |
|---|---|---|
| **IQ** — is the system installed as specified? | The right software, at the right version, is what actually runs. | Every module container is pinned by `@sha256` digest ([ADR-0009](adr/0009-docker-pinned-by-digest.md)), guarded by `tests/test_container_pinning.py`; the caller's version and the checksums of every input reach `run_provenance`, container identity does not yet (§6). CDK guardrail tests (`infra/test/stacks.test.ts`) assert infrastructure invariants — bucket versioning, public-access block, TLS-only, IAM deny-delete — before any environment is considered correctly installed. |
| **OQ** — does the system operate correctly across its intended range? | The pipeline runs end-to-end and produces the expected artifacts under normal and stub conditions. | The Nextflow `-stub` profile (`pipeline/main.nf`) exercises every process's structure without real compute; `pytest` covers the provenance/guardrail logic deterministically (`tests/test_build_metrics.py` and this repo's other `tests/test_*.py` files); CI (`.github/workflows/`) runs both on every change. |
| **PQ** — does the system perform correctly against real-world data and acceptance criteria? | The actual analytical result meets a defined, justified threshold. | The `hap.py`-vs-GIAB benchmark in §4 of this document, against the SNV F1 ≥ 0.99 acceptance criterion in §3, run on real GIAB HG002 reads (not synthetic/stub data) — the result recorded per run as `validation_pass` in `metrics.json` and stored insert-only in `db/schema.sql` (recorded, not yet enforced as a gate — see §3). |

This mapping is a vocabulary bridge, not new validation work — every cited mechanism already
existed before this section was written. What it does not claim: formal IQ/OQ/PQ protocol
documents with named approvers, a quality management system, or any regulatory submission.
Those are organizational processes this solo portfolio project has no occasion to build.
