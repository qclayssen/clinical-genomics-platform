# Analytical Validation Report

**Assay:** Germline single-nucleotide variant (SNV) calling, whole-genome sequencing
**Scope of this validation:** GRCh38, chromosome 20
**Reference material:** GIAB HG002 / NA24385 (Ashkenazi son), NIST benchmark v4.2.1
**Comparator:** `hap.py` (vcfeval engine) against the v4.2.1 high-confidence VCF + BED

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

_Populate from your own `hap.py` run — do not ship placeholder numbers as if measured._

| Caller | SNV precision | SNV recall | SNV F1 | INDEL F1 | Ti/Tv | Mean depth |
|---|---|---|---|---|---|---|
| GATK HaplotypeCaller | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ |
| DeepVariant | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ |

## 5. Known limitations

- Validated on **chr20 only**; performance is not claimed genome-wide.
- Low-complexity / segmental-duplication regions are excluded by the GIAB
  high-confidence BED and are therefore **out of scope** of this validation.
- INDEL performance reported for information; the acceptance criterion is SNV-only.
- Truth set is a single sample (HG002); this is not a cohort validation.

## 6. Provenance of this validation

Every result row is traceable to: pipeline git commit, container image digests, the
reference build (`GRCh38.p14`), the truth-set version (`GIAB-v4.2.1`), and SHA-256
checksums of all inputs — captured automatically in `run_provenance`.

## 7. Change control

Any change to reference, caller, or filtering re-triggers this validation before the
new pipeline version is tagged in `CHANGELOG.md`. Re-validation on change is the point.
