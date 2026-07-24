# Context (DOC intel)

Running notes from the 17 DOC-classified sources, keyed by topic. Lowest precedence — where a
DOC contradicts an ADR or SPEC, the higher-precedence source wins and the DOC is treated as
narrative or as a dated record.

---

## Topic: project identity and honesty posture

- source: `docs/FOR-RECRUITERS.md` — one-page overview mapping demonstrated skills to evidence
  locations. Explicitly separates "verified running" from "needs environment". Provides a
  reading order for reviewers.
- source: `docs/BEGINNERS-GUIDE.md` — plain-language walkthrough for readers with no
  bioinformatics background: FASTQ -> QC -> alignment (BWA-MEM2) -> mark duplicates -> variant
  calling -> GIAB truth-set comparison -> provenance -> database -> dashboard -> AI summary.
- source: `docs/GLOSSARY.md` — every project term defined simply (DNA, sequencing, WGS,
  reference genome, variant calling, SNV, pipeline, provenance, guardrails). Mutually linked
  with BEGINNERS-GUIDE.
- theme: the repo's stated credibility principle is *not overclaiming*. `docs/ROADMAP.md`
  states it directly: "Every item below either produces measured evidence or closes a gap
  between what the docs say and what the code does. Nothing here invents a new capability to
  look impressive."

## Topic: validation evidence

- source: `docs/VALIDATION.md` — the analytical validation report, structured after an ISO
  15189 validation. Assay: germline SNV calling. Reference material GIAB HG002 / NA24385 NIST
  benchmark v4.2.1. Comparator `hap.py` **xcmp engine** (cites ADR-0015). Acceptance criterion
  SNV F1 >= 0.99, recorded as `validation_pass`, enforced by DB/dashboard; runs below
  threshold are flagged and withheld from reporting until reviewed.
- measured result (2026-07-15, real non-stub run): GATK HaplotypeCaller — SNV precision 0.9934,
  SNV recall 0.9894, SNV F1 0.9914, INDEL F1 0.9971, Ti/Tv 2.07, mean depth 255.8x.
  DeepVariant not yet run.
- stated limitations: validated on a **chr20:1,000,000-2,000,000 (1 Mb) window**, not full
  chr20 — narrower than ADR-0001; extending is mechanical (drop `--intervals`, use the full
  11 GB BAM) but not done. Depth 255.8x is unrepresentative (source BAM is 300x, no
  downsampling). xcmp is slightly more conservative than vcfeval on complex representations.
  Low-complexity / segmental-duplication regions excluded by the high-confidence BED. Single
  sample, not a cohort validation.
- source: `docs/END-TO-END.md` — a **dated record of the 2026-07-14 run**, one day before the
  real validation. It states accuracy numbers were "not real yet" and `VALIDATION.md` remained
  placeholder. That was accurate on its date and has since been superseded by the 2026-07-15
  measured run. Not a contradiction — a run log.
- what END-TO-END.md does establish as really executed: Nextflow 26.04 ran the 9-process DAG
  `-profile test -stub` with completed=9 failed=0; `build_metrics.py` produced a metrics.json
  with populated `provenance.input_checksums`; real Postgres 16 schema applied and ingested;
  **insert-only triggers verifiably rejected `UPDATE runs` and `DELETE FROM audit_log`**;
  all Metabase card SQL ran against real Postgres via `v_run_summary`; `infer.py --offline`
  produced a guardrailed summary with banner, field citations and provenance line;
  `ga4gh_ids.py` produced `ga4gh:SQ.yPq8nYZW4UK4yIUDlSnzD5QoojYjv75a`; full pytest suite passed.

## Topic: how to run the platform

- source: `docs/RUNBOOK.md` — step-by-step guide to run the pipeline locally on staged GIAB
  HG002 chr20 data and record measured validation metrics. References `scripts/preflight.sh`,
  `scripts/fetch_testdata.sh`, `pipeline/main.nf`, `pipeline/bin/ga4gh_ids.py`.
- source: `docs/SOP-run-pipeline.md` — standard operating procedure covering local and AWS
  execution, validation and review steps, AI report review, audit log. **Note:** the SOP still
  references AWS Batch as the cloud execution path; that reference is stale post-ADR-0011.
- source: `docs/usage.md` — reference for samplesheet, pipeline parameters, Nextflow profiles,
  reference genome, truth set, variant caller and Postgres ingest. Also references an
  `aws.config` Batch profile (stale post-ADR-0011).
- source: `docs/output.md` — the `results/` directory layout and which module produces each
  file: QC reports, alignment, variant calls, hap.py validation, metrics.json, provenance,
  MultiQC.

## Topic: standards alignment

- source: `docs/GA4GH-ALIGNMENT.md` — status table with an explicit honesty legend
  (Implemented / Partial / Aspirational / N/A here):
  - **refget — Implemented** (`pipeline/bin/ga4gh_ids.py`, spec known-answer test:
    `sha512t24u(b"ACGT") == "aKF498dAxcJAqme6QYQ7EZ07-fiw8Kw2"`)
  - **VRS — Partial** (shared `sha512t24u` primitive + a simplified allele-digest helper; full
    VRS needs the `ga4gh.vrs` library)
  - **WES, DRS, Phenopackets, htsget, service-info — Aspirational**
  - **Crypt4GH, Passport/AAI + Data Use Ontology — N/A here** (public GIAB data)

## Topic: architecture evolution and migration

- source: `docs/PRODUCTION-MIGRATION.md` — maps each free-tier component to its production
  counterpart and satisfies SPEC Requirement 15 in full:
  - Pipeline: Lambda + Step Functions -> **AWS HealthOmics** private workflows (managed
    Nextflow; `main.nf` and all 12 modules upload directly, Biocontainers directives unchanged;
    no timeout constraints, native `resume`, HIPAA-eligible). $50-500/month.
  - Data store: DynamoDB -> **Aurora Serverless v2** (existing `db/schema.sql` adopts directly;
    append-only translates to `REVOKE DELETE, UPDATE` grants). $30-200/month.
  - AI reporting: FAISS + Ollama -> **Bedrock + Knowledge Bases** (banner -> content policy
    mandatory prefix; phrase scrubbing -> denied topics; provenance citation -> grounding
    policy with source attribution). $10-100/month.
  - Fine-tuning: local QLoRA -> **SageMaker Training + Model Registry** (managed spot
    `ml.g5.xlarge`; `train_lora.py` packages as the job entry point). $5-50/run.
  - Demo total $0/month; production estimate $95-850/month.
- source: `docs/NEXTFLOW-MIGRATION.md` — issues, symptoms, causes and fixes from migrating to
  Nextflow 26 strict-DSL and nf-core conventions (DSL2 parser, `publishDir`, `versions.yml`,
  `nextflow_schema.json`, CI lint).

## Topic: build status and planning

- source: `docs/MILESTONES.md` — milestones M0-M8 (scaffold -> core pipeline -> validation ->
  containers/CI -> CDK infra -> Postgres -> Metabase -> QLoRA -> README/demo). Current status
  table reports every layer scaffolded or implemented, **"Architecture Decision Records
  (16 ADRs) — written"**, and a runnable Streamlit demo app (`demo/`) with explorer, variant
  interpretation and assistant pages that needs no database, cloud account or LLM.
  **Note:** milestone M4's demoable artifact still reads "the same pipeline runs on AWS Batch
  unmodified" — stale post-ADR-0011.
- source: `docs/ROADMAP.md` — P0-P3 prioritized plan for the **non-serverless** parts only.
  Explicitly declares the serverless migration and RAG reporter out of scope for this roadmap
  (owned by the Kiro spec, tasks 1-16) and instructs against double-tracking them.
  P0-1 and P0-2 (write ADR-0011 and ADR-0012, set ADR-0004/0005 to Superseded, update the ADR
  index) are now **done** — both ADRs exist and both statuses are set. The index update is
  still outstanding.
  ROADMAP.md's stated highest-ROI action (run real GIAB chr20 and replace `_fill_`
  placeholders) is marked done, matching the measured numbers in VALIDATION.md.
- source: `docs/adr/README.md` — the ADR index and process description. **Stale: lists 12 ADRs;
  the repo now has 16.** ADRs 0013-0016 are missing from the index table.
- source: `docs/GITHUB-SETUP.md` — authenticating with GitHub and pushing via
  `scripts/push_to_github.sh` and the `gh` CLI. Operational only; no planning impact.

## Topic: governance conventions (from CLAUDE.md, reinforced across docs)

- ADRs are append-only. A new choice is the next-numbered file; an old ADR is never rewritten —
  it is superseded and its status updated. Reciprocal supersedes / superseded-by backlinks
  between ADR pairs are the required convention.
- Insert-only results/provenance; corrections are new rows, never edits.
- Every result carries a provenance stamp; fields are never removed from it.
- AI output always passes `enforce_guardrails()`.
- Re-validate on change: any change to reference, caller or filtering re-triggers hap.py-vs-GIAB
  validation before tagging. Acceptance criterion SNV F1 >= 0.99.

## Topic: known documentation drift (all lowest-precedence, no decision impact)

- `docs/adr/README.md` index stops at ADR-0012.
- `docs/ROADMAP.md` reserves `docs/adr/0014-spatial-genomics-direction.md` — number 0014 was
  taken by the agentic variant interpretation ADR. A spatial-genomics ADR needs a free number.
- `docs/SOP-run-pipeline.md`, `docs/usage.md` and `docs/MILESTONES.md` (M4) still describe AWS
  Batch as the cloud execution path.
- `docs/END-TO-END.md` describes validation numbers as placeholder; superseded by the
  2026-07-15 measured run in `docs/VALIDATION.md`.
