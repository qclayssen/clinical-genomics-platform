# SOP — Running the Germline SNV Pipeline

**Document ID:** CGP-SOP-001 · **Version:** 1.0.0 · **Status:** portfolio demonstration

> Written in standard operating procedure shape (scope / procedure / acceptance /
> deviations) to demonstrate familiarity with ISO 15189 documentation, not as a
> controlled clinical document.

## 1. Scope

Applies to germline SNV analysis of paired-end WGS FASTQs against GRCh38, run locally
with Nextflow + Docker. Cloud orchestration (Lambda + Step Functions) handles metadata
and provenance recording. Out of scope: somatic calling, structural variants, non-human samples.

## 2. Responsibilities

| Role | Responsibility |
|---|---|
| Operator | Prepares the sample sheet, launches the run, checks it completed |
| Reviewer | Confirms `validation_pass = true` and signs off AI-drafted summaries |

## 3. Materials

- Reference: `GRCh38_chr20.fa` (+ indexes) — staged by `scripts/fetch_testdata.sh`
- Truth set: GIAB HG002 v4.2.1 (validation runs only)
- Containers: pinned per module (see `docker/`)

## 4. Procedure

1. **Prepare inputs.** Add one row per sample to `pipeline/assets/samplesheet.csv`
   conforming to `assets/schema_input.json`.
2. **Dry run.** `nextflow run main.nf -profile test,docker -stub` — confirm the DAG resolves.
3. **Execute.** `nextflow run main.nf -profile test,docker` (real data requires staged GIAB
   HG002 chr20 via `scripts/fetch_testdata.sh`). Cloud orchestration (if deployed) records
   metadata and provenance to DynamoDB; the genomics compute runs locally.
4. **Verify completion.** Check the `onComplete` banner reports `SUCCESS` and that
   `results/<sample>/export/<sample>.metrics.json` exists.
5. **Confirm acceptance.** Confirm `validation_pass = true` (below-threshold runs stop here).
6. **Draft report.** `python ai-report/infer.py --metrics <path> --offline` (or with an adapter).
7. **Human review.** Reviewer reads the draft against the metrics and signs off. The
   `AI-DRAFTED — REQUIRES CLINICIAN REVIEW` banner must remain until signed.

## 5. Acceptance criteria

- Pipeline exits `SUCCESS`; MultiQC report generated.
- `validation_pass = true` (SNV F1 ≥ 0.99) for validation samples.
- Provenance record written with input checksums.

## 6. Deviation handling

Any deviation (tool version change, threshold miss, aborted run) is recorded as a new
`audit_log` entry and, if it affects performance, triggers re-validation (§7 of
`VALIDATION.md`). No result is amended in place — a corrected run is a new record.

## 7. Records

`runs`, `qc_metrics`, `run_provenance`, `audit_log` (Postgres) + Nextflow
`provenance/` reports (timeline, trace, DAG) + S3 versioned objects.
