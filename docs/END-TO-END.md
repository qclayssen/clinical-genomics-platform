# End-to-end run evidence

A real execution of the platform's full data flow, run on 2026-07-14. This documents what
was **actually executed** (not simulated) and — honestly — the one stage that still needs a
containerized run on real data.

## What ran for real

| Stage | Executed | Evidence |
|---|---|---|
| **Pipeline orchestration** | Nextflow 26.04 ran the full 9-process DAG (QC → align → mark-dup → call → hap.py → JSON/Parquet export → MultiQC) end-to-end, `-profile test -stub` | `[SUCCESS] completed=9 failed=0`; outputs under `results/`, provenance reports (timeline/report/trace/dag) under `results/provenance/` |
| **Structured output + provenance** | `build_metrics.py` produced a `metrics.json` with git commit, versions, and SHA-256 input checksums | `provenance.input_checksums` populated |
| **Database (real Postgres 16)** | Schema applied; `ingest_metrics.py` wrote `runs` + `qc_metrics` + `run_provenance` + `audit_log` | 1 ingested run + 6 seeded; `audit_log` INGEST row present |
| **Insert-only guarantee** | `UPDATE runs` and `DELETE FROM audit_log` were **rejected by DB triggers** | `ERROR: Table runs is insert-only (append a correction instead)` |
| **Dashboard queries** | All Metabase card SQL ran against real Postgres via `v_run_summary` | pass-rate 100% (7 runs); F1-by-version 0.2.0/gatk 0.9957 → 0.3.0/deepvariant 0.9986 |
| **AI reporting** | `infer.py --offline` produced a guardrailed summary | banner + field citations + provenance line present |
| **GA4GH refget ID** | `ga4gh_ids.py` produced a content-based `ga4gh:SQ.` identifier for the reference | `ga4gh:SQ.yPq8nYZW4UK4yIUDlSnzD5QoojYjv75a` |
| **Tests** | Full pytest suite | 12 passed |

## What this run does NOT prove (and why)

- **Accuracy numbers are not real yet.** The DAG ran in **stub mode** (each step writes
  placeholder outputs) because the heavy bioinformatics tools (bwa-mem2, GATK, DeepVariant,
  hap.py) run in **Docker containers on real GIAB WGS data**, which needs a Docker daemon and
  multi-GB downloads not available in the run environment. The precision/recall/F1 shown above
  are from committed **fixtures / demo seed data**, not a measured `hap.py` run — so
  `docs/VALIDATION.md` remains placeholder, correctly.
- To produce **measured** accuracy, run the same pipeline with `-profile docker` on real data
  on a machine with Docker — see [RUNBOOK.md](RUNBOOK.md). Everything downstream (DB, dashboard,
  AI report, GA4GH id) is already proven to work and will consume those real outputs unchanged.

## Fixes made to get here

Running on current Nextflow (26.04) surfaced real compatibility issues, now fixed:

- `nextflow.config`: replaced the deprecated `check_max()` function with `resourceLimits`
  (the modern nf-core idiom); memory/time as typed literals.
- `main.nf`: moved the top-level provenance block inside `workflow {}` and removed the
  `onComplete` handler (strict-DSL rule: no statements mixed with declarations).
- All modules: `publishDir "…${meta.id}…"` → closure form `publishDir { "…" }` (required to
  reference input vars under the strict engine).
- CI: the stub job now uses `-profile test` (no `docker`) — stub runs need no containers.

## Reproduce the runnable parts locally

```bash
# pipeline DAG (needs Java + Nextflow; no Docker)
cd pipeline && nextflow run main.nf -profile test -stub

# database + dashboard (needs local Postgres)
createdb cgp && psql cgp -f ../db/schema.sql -f ../db/seed_demo.sql
python ../pipeline/bin/ingest_metrics.py --db-url "$CGP_DB_URL" --metrics <metrics.json> --vcf <vcf> --log /tmp/i.log

# AI report + GA4GH id (dependency-free)
python ../ai-report/infer.py --metrics <metrics.json> --offline
python ../pipeline/bin/ga4gh_ids.py --fasta <reference.fa>
```
