# Analytical Validation Report

**Assay:** Germline single-nucleotide variant (SNV) calling, whole-genome sequencing
**Scope of this validation:** GRCh38, chromosome 20, region chr20:1,000,000-2,000,000 (see
§5 Known limitations — this run covers a 1 Mb window, not the full chromosome)
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

1. Reads processed through the standard pipeline (`fastp` → `bwa-mem2` → MarkDuplicates
   → HaplotypeCaller/DeepVariant).
2. Output VCF compared to the GIAB truth VCF, restricted to the high-confidence BED.
3. Metrics parsed from `hap.py summary.csv` into `metrics.json` (see `build_metrics.py`).

## 3. Acceptance criterion

- **SNV F1 ≥ 0.99** within the high-confidence regions.
- Recorded per run as `validation_pass` and enforced by the DB/dashboard.
- A run below threshold is flagged; results are withheld from reporting until reviewed.

## 4. Results

Measured 2026-07-15 from a real, non-stub run: real GIAB HG002 reads (NIST
`HG002.GRCh38.300x_chr20.bam`, remotely region-extracted to chr20:1,000,000-2,000,000),
real GRCh38 chr20 reference, real GIAB v4.2.1 truth VCF/BED, run through the actual
Nextflow pipeline (`fastp` → `bwa-mem2` → MarkDuplicates → HaplotypeCaller → `hap.py`) in
Docker. Truth BED was intersected to the same window before comparison, so the pipeline's
calling scope and the benchmarking scope match (see the note in §5 about the two truth-set
scoping bugs this run surfaced and fixed).

| Caller | SNV precision | SNV recall | SNV F1 | INDEL F1 | Ti/Tv | Mean depth |
|---|---|---|---|---|---|---|
| GATK HaplotypeCaller | 0.9934 | 0.9894 | 0.9914 | 0.9971 | 2.07 | 255.8x |
| DeepVariant | _not yet run_ | _not yet run_ | _not yet run_ | _not yet run_ | _not yet run_ | _not yet run_ |

SNV F1 = 0.9914 meets the ≥ 0.99 acceptance criterion (§3); `validation_pass: true` in the
run's `metrics.json`.

## 5. Known limitations

- Validated on a **chr20:1,000,000-2,000,000 (1 Mb) window**, not the full chromosome —
  narrower than the "chr20" scope in [ADR-0001](adr/0001-scope-giab-hg002-chr20.md). A
  full-chromosome run needs the full `HG002.GRCh38.300x_chr20.bam` (11 GB) rather than a
  region-restricted pull; this run used the smaller, region-restricted extraction to stay
  laptop-feasible. Extending to full chr20 is mechanical (drop `--intervals`, use the whole
  BAM) but not yet done.
- Depth (255.8x) is high because the source BAM is 300x-coverage GIAB data and no
  downsampling was applied for this run; it is not representative of typical 30-40x
  clinical WGS depth. A future run should downsample to a realistic depth for a more
  representative precision/recall figure.
- Comparison uses `hap.py`'s **xcmp** engine, not vcfeval — see
  [ADR-0015](adr/0015-happy-xcmp-engine-not-vcfeval.md) for why (the pinned container lacks
  `rtg-tools`, and the alternative image bundling it can't be pulled with modern Docker).
- Low-complexity / segmental-duplication regions are excluded by the GIAB
  high-confidence BED and are therefore **out of scope** of this validation.
- INDEL performance reported for information; the acceptance criterion is SNV-only.
- Truth set is a single sample (HG002); this is not a cohort validation.
- DeepVariant has not yet been run for a real comparison row.

## 6. Provenance of this validation

Every result row is traceable to: pipeline git commit, container image digests, the
reference build (`GRCh38.p14`), the truth-set version (`GIAB-v4.2.1`), and SHA-256
checksums of all inputs — captured automatically in `run_provenance`.

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
| **IQ** — is the system installed as specified? | The right software, at the right version, is what actually runs. | Docker images pinned by SHA-256 digest, not floating tags ([ADR-0009](adr/0009-docker-pinned-by-digest.md)); every run's exact tool/container identity is captured in `run_provenance` (§6). CDK guardrail tests (`infra/test/stacks.test.ts`) assert infrastructure invariants — bucket versioning, public-access block, TLS-only, IAM deny-delete — before any environment is considered correctly installed. |
| **OQ** — does the system operate correctly across its intended range? | The pipeline runs end-to-end and produces the expected artifacts under normal and stub conditions. | The Nextflow `-stub` profile (`pipeline/main.nf`) exercises every process's structure without real compute; `pytest` covers the provenance/guardrail logic deterministically (`tests/test_build_metrics.py` and this repo's other `tests/test_*.py` files); CI (`.github/workflows/`) runs both on every change. |
| **PQ** — does the system perform correctly against real-world data and acceptance criteria? | The actual analytical result meets a defined, justified threshold. | The `hap.py`-vs-GIAB benchmark in §4 of this document, against the SNV F1 ≥ 0.99 acceptance criterion in §3, run on real GIAB HG002 reads (not synthetic/stub data) — the result recorded per run as `validation_pass` in `metrics.json` and enforced insert-only in `db/schema.sql`. |

This mapping is a vocabulary bridge, not new validation work — every cited mechanism already
existed before this section was written. What it does not claim: formal IQ/OQ/PQ protocol
documents with named approvers, a quality management system, or any regulatory submission.
Those are organizational processes this solo portfolio project has no occasion to build.
