---
name: clinical-genomics
description: Working in the Clinical Genomics Insight Platform repo — how to run/extend the Nextflow pipeline, the provenance & AI-guardrail rules, the validation workflow, and the ADR process.
---

# Clinical Genomics Insight Platform — how-to knowledge

Portfolio germline-SNV platform scoped to GIAB HG002 chr20. Read `CLAUDE.md` first for the
repo map and design rules; this skill is the practical how-to for extending it. Nothing here
overrides the non-negotiables: insert-only provenance, guardrailed AI, digest-pinned
containers, append-only ADRs, re-validate on change.

## 1. Add a new pipeline module

Modules are nf-core-style, **one process per file** under `pipeline/modules/<group>/<tool>.nf`.

1. **Copy an existing module** as the template — e.g. `pipeline/modules/qc/fastp.nf` (simple
   I/O) or `pipeline/modules/validate/happy_benchmark.nf` (multiple inputs/outputs). Keep the
   shape: `tag`, `label`, `container`, `publishDir`, typed `input:`/`output:` with `emit:`
   names, a `script:` block, and a **`stub:` block**.
2. **Reference a digest-pinned container** (`quay.io/biocontainers/<tool>@sha256:…` in
   production; a Biocontainers tag is acceptable while prototyping). One tool per image — do
   not fold unrelated tools together (ADR-0009).
3. **Always include a `stub:` block** that writes plausible placeholder outputs with the same
   filenames the real `script:` emits. This is what makes `nextflow run main.nf -profile
   test,docker -stub` resolve the DAG with no tools/data installed — the stub run is CI and the
   fast local sanity check, so a module with no stub breaks it.
4. **Wire it into `pipeline/main.nf`:** add an `include { NAME } from './modules/<group>/<tool>.nf'`
   at the top, then call it in the `workflow {}` block, feeding it upstream `.out.<emit>`
   channels. If it produces metrics that belong in the record, join them into the
   `JSON_METRICS(...)` input so they land in `metrics.json` with provenance — do not create a
   side-channel output that skips the provenance stamp.
5. **Validate:** `cd pipeline && nextflow run main.nf -profile test,docker -stub` and confirm
   the DAG resolves and your process appears.

## 2. The provenance / `metrics.json` contract (keep it insert-only)

- The provenance stamp is assembled once in `main.nf` (`def provenance = [...]`: pipeline
  version, git commit, run id, start time, reference build, truth version) and threaded into
  `JSON_METRICS`.
- `pipeline/bin/build_metrics.py` merges that stamp with parsed QC (`parse_dup_metrics`),
  validation (`parse_happy`), and **SHA-256 checksums of every input** (`sha256`) into the
  final `metrics.json`. `pipeline/bin/ingest_metrics.py` writes it to Postgres.
- **Why it must stay insert-only:** the DB tables (`runs`, `qc_metrics`, `run_provenance`,
  `audit_log`) reject UPDATE/DELETE via the `forbid_mutation()` trigger in `db/schema.sql`. A
  correction is a **new run row**, never an edit — this is the ISO-15189-style record-amendment
  pattern (ADR-0005). Never add an update/delete path, and never drop provenance fields; the
  whole platform's credibility rests on this being reconstructable.
- When you change what a run produces, extend `build_metrics.py` **and** its tests in
  `tests/test_build_metrics.py` in the same change.

## 3. The AI reporting contract

`ai-report/infer.py` drafts a plain-language summary **from `metrics.json` only** — the model
never sees raw reads or the VCF body.

**Guardrails that must never be removed** (`enforce_guardrails()`, ADR-0008): the
`AI-DRAFTED — REQUIRES CLINICIAN REVIEW` banner is re-inserted if absent, the `Provenance:`
line is guaranteed, and advice phrasing (`we recommend`, `diagnos…`, `treat… with`) is scrubbed
to `[review required]`. Every code path routes through this function before output. These
behaviours are unit-tested in `tests/test_build_metrics.py` — if you touch `infer.py`, those
tests must stay green.

**Three execution paths (graceful degradation):**
1. `--adapter PATH` — QLoRA fine-tuned adapter over the base model (needs a GPU).
2. default — zero-shot fallback prompt (`ai-report/prompts/fallback_prompt.md`) against a base
   instruct model.
3. `--offline` — deterministic template renderer, **no ML deps at all**; guarantees a compliant
   report for CI and demos.

**Run the smoke test** to prove the training loop without a GPU:
`python ai-report/train_smoke.py` (needs `torch transformers datasets peft`; uses
`ai-report/data/report_pairs.sample.jsonl`, ~1 min). The tiny model's text is gibberish by
design — the point is that data → LoRA → train → save → generate runs.

## 4. Record a new architecture decision

Decisions live in `docs/adr/` as `NNNN-short-title.md`, numbered sequentially and **never
renumbered or rewritten**.

1. Create the **next unused number** — check `ls docs/adr/` rather than trusting this line;
   the highest is currently `0017`. Follow the existing structure: Status, Context, Decision,
   Consequences, Alternatives considered.
2. Add a row to the index table in `docs/adr/README.md`.
3. To change a past decision, add a **new** ADR that supersedes it and set the old one's status
   to `Superseded by ADR-XXXX` — same append-only principle as the database. Do not silently
   edit history.

## 5. Validation workflow

- Benchmark SNV calls with **`hap.py`** (xcmp engine — ADR-0015, not vcfeval; the pinned
  container lacks `rtg-tools`) against the **GIAB HG002 v4.2.1** high-confidence VCF + BED,
  restricted to chr20 (ADR-0003, `docs/VALIDATION.md`).
- **Acceptance criterion: SNV F1 ≥ 0.99** within the high-confidence regions. Recorded per run
  as `validation_pass`; below-threshold runs are flagged and withheld from reporting.
- **Re-validate on any change** to reference, caller, or filtering *before* tagging a new
  pipeline version in `CHANGELOG.md`. This is the point of the whole exercise — do not change a
  tool version or filter and skip re-validation.
- Do not commit placeholder numbers to `docs/VALIDATION.md` as if measured; the results table is
  populated from a real `hap.py` run.
- Full validation needs Nextflow + Docker + staged GIAB data (`scripts/fetch_testdata.sh`); the
  Python parsing/threshold logic is exercised offline by `pytest`.
