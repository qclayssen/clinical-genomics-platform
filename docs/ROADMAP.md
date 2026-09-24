# Roadmap — rest of the project

An honest, prioritized next-steps plan for the **non-serverless** parts of the platform.
Phases run **P0 (do now) → P3 (later)**. Each item lists *what*, *why it matters for the job
hunt*, rough *effort* (S ≈ hours, M ≈ 1–2 days, L ≈ a week+), and *dependencies*.

Tone note: this repo's credibility comes from *not overclaiming*. Every item below either
produces measured evidence or closes a gap between what the docs say and what the code does.
Nothing here invents a new capability to look impressive.

> **Single highest-ROI next action:** ~~run the pipeline on real GIAB HG002 chr20 and replace the
> `_fill_` placeholders~~ ✅ Done — real numbers now in [`docs/VALIDATION.md`](VALIDATION.md) and
> the README table, with the raw evidence committed under
> [`docs/validation-evidence/HG002_chr20/`](validation-evidence/HG002_chr20/). P0-1 through P0-3
> and most of P1-4 (diagram, demo GIFs, public repo) are all done — see the updated status below.
> Next priority: **P1-1**, the last open item in this phase (real `versions.yml` collation, a
> clean `nf-core lint` pass, and `nf-test` coverage).

---

## Owned by Kiro spec (not tracked here)

The **serverless infrastructure migration** (Lambda + Step Functions + DynamoDB) and the
**RAG reporter** (FAISS + Ollama) are owned by the Kiro spec and tracked in
[`.kiro/specs/clinical-genomics-platform/tasks.md`](../.kiro/specs/clinical-genomics-platform/tasks.md)
(Kiro AI-assisted spec — a structured planning feature in the Kiro IDE used to develop this project).
Do **not** re-plan or double-track them here. Specifically out of scope for this roadmap:

- `metadata-stack.ts` (DynamoDB single-table), `orchestration-stack.ts` (Step Functions +
  EventBridge), per-Lambda IAM roles, serverless observability (Kiro tasks 1–6).
- The seven Lambda handlers under `lambdas/` and the DynamoDB→Postgres sync (Kiro tasks 7, 10).
- The RAG layer under `ai-report/rag/` — FAISS index, retriever, Ollama-augmented `infer.py`
  (Kiro tasks 9, 12.11–12.12).
- The property-based test suite, updated CDK guardrail tests, CI updates, and
  `docs/PRODUCTION-MIGRATION.md` (Kiro tasks 12–16).

This roadmap only picks up the **consequences** those changes leave behind for docs/governance
(P0-1, P0-2) — it does not touch the serverless build itself.

---

## P0 — Do now (cheap, unblocking, or highest-credibility)

### P0-1 · ADR-0011: supersede ADR-0004 (Batch/Fargate → serverless) ✅ Done
- **What:** Write `docs/adr/0011-serverless-lambda-stepfunctions.md`. Status `Accepted`; record
  the decision to move compute from AWS Batch/Fargate to Lambda + Step Functions + EventBridge.
  Set [ADR-0004](adr/0004-aws-cdk-batch-fargate.md) status to `Superseded by ADR-0011` and add
  ADR-0011 to the index table in [`docs/adr/README.md`](adr/README.md).
- **Status:** Complete — ADR-0011 through ADR-0017 are now written and indexed.
- **Effort:** S · **Depends on:** nothing (pure docs).

### P0-2 · ADR-0012: supersede ADR-0005 (insert-only Postgres → DynamoDB primary) ✅ Done
- **What:** Write `docs/adr/0012-dynamodb-primary-store.md`. Status `Accepted`; DynamoDB
  single-table becomes the primary metadata store, Postgres becomes a Metabase read-bridge fed by
  the DynamoDB→Postgres sync. Set [ADR-0005](adr/0005-insert-only-postgres.md) to
  `Superseded by ADR-0012`; update the index.
- **Status:** Complete — ADR-0012 written and indexed. The integrity nuance (IAM-based vs.
  database-trigger enforcement) is documented in ADR-0012's Consequences section.
- **Effort:** S · **Depends on:** nothing (docs).

### P0-3 · Real validation numbers (the credibility keystone)
- **What:** Follow [`docs/RUNBOOK.md`](RUNBOOK.md) end-to-end on a machine with Docker: stage GIAB
  HG002 chr20 (`scripts/fetch_testdata.sh` + real reads), `scripts/preflight.sh`, then
  `nextflow run main.nf -profile docker …`. Copy the **measured** precision/recall/F1/Ti-Tv from
  `results/HG002_chr20/validation/*.happy.summary.csv` into [`docs/VALIDATION.md`](VALIDATION.md)
  §4 and the README table, replacing every `_fill_`. Optionally run `--caller deepvariant` for the
  comparator row. Record the truth version, reference build, and pipeline git commit alongside.
- **Why it matters:** Everything downstream (DB ingest, dashboard, AI report, GA4GH refget id) is
  **already proven to run** on stub/fixture data per [`docs/END-TO-END.md`](END-TO-END.md); the one
  thing not yet real is the accuracy table — and that table is the single most scrutinized artifact
  a clinical-bioinformatics reviewer will open. It turns "validation methodology" into "validated,
  F1 = 0.99x". It is the prerequisite for honest resume bullets (P1-3) and for going public (P1-4).
- **Effort:** M (mostly wall-clock: ~30 min setup + one run) · **Depends on:** Docker on the
  user's machine (not CI). **This is the highest-ROI item in the whole roadmap.**

---

## P1 — Near-term (finish what's started; make it presentable)

### P1-1 · Pipeline finalization — nf-core migration loose ends
- **What:** Three sub-items, do together:
  1. **Real `versions.yml` collation.** `pipeline/main.nf` currently merges per-process fragments
     with `collectFile` (a raw concat, done as an operator rather than a process so it adds no
     extra task to the stub DAG). Replace with a proper
     collation step in the nf-core idiom (a `CUSTOM_DUMPSOFTWAREVERSIONS`-style process that
     de-duplicates and emits a clean `software_versions.yml` + a MultiQC-ingestible table).
  2. **Clean `nf-core lint` pass.** Reconcile [`.nf-core.yml`](../.nf-core.yml) ignores with reality
     and drive the lint warnings to zero (or to a documented, justified ignore list). This is a
     hand-written pipeline, not template-generated, so some ignores are legitimate — document which.
  3. **`nf-test` tests.** There are currently **no** `*.nf.test` files or `nf-test.config`. Add
     nf-test coverage for at least the QC, call, and validate modules plus a workflow-level test, so
     module behaviour is pinned beyond the `-stub` DAG check.
- **Why it matters:** "nf-core-style Nextflow" is the headline skill on
  [`docs/FOR-RECRUITERS.md`](FOR-RECRUITERS.md). A green `nf-core lint`, real version-tracking, and
  `nf-test` are exactly what a UMCCR-style reviewer greps for to tell "wrote nf-core" from "wrote
  Nextflow that looks nf-core-ish."
- **Effort:** M · **Depends on:** ideally after P0-3 (a real run surfaces version strings and lint
  edge-cases that stub mode hides).

### P1-2 · Document the Nextflow migration issues — drafted, pending P1-1
- **What:** Create `docs/NEXTFLOW-MIGRATION.md` capturing the strict-DSL / Nextflow 26.04
  compatibility fixes. The raw material already exists in [`docs/END-TO-END.md`](END-TO-END.md)
  ("Fixes made to get here": `check_max()` → `resourceLimits`, provenance block moved inside
  `workflow {}`, `publishDir` closure form, stub CI profile change) — promote it into a standalone
  migration note and extend it with the P1-1 changes (versions collation, lint, nf-test).
- **Status:** `docs/NEXTFLOW-MIGRATION.md` exists and covers the strict-DSL and nf-core
  convention issues; it honestly flags versions collation, `nf-core lint`, and `nf-test` as
  still-open follow-ups in its own "Process / follow-ups" section — this task closes out once
  P1-1 lands and the doc gets a short update rather than a rewrite.
- **Why it matters:** Shows you can *maintain* a pipeline across a breaking engine upgrade, not just
  author one — a concrete, senior-signal artifact and good interview fodder.
- **Effort:** S · **Depends on:** P1-1 (so the doc is complete, not partial).

### P1-3 · Real resume bullets backed by measured numbers
- **What:** Draft 3–5 resume/LinkedIn bullets that cite the **P0-3 measured** figures (e.g. "SNV
  F1 = 0.99x vs GIAB v4.2.1 truth on chr20 via hap.py"), the architecture facts (Nextflow DSL2 →
  serverless AWS, insert-only/append-only provenance, GA4GH refget), and the guardrailed LLM.
- **Why it matters:** This is the direct job-hunt payload. Bullets that quote a real F1 read very
  differently from "built a validation pipeline."
- **Effort:** S · **Depends on:** P0-3 (do **not** write number-bearing bullets before the run —
  placeholder numbers on a resume is the one unrecoverable credibility mistake).

### P1-4 · Portfolio polish — architecture diagram + demo GIF, then go public ✅ Done
- **What:** (a) Replace the ASCII architecture block in [`README.md`](../README.md) with a rendered
  diagram (and update it for the serverless topology once Kiro's migration settles). (b) Record a
  ~3-minute demo GIF/clip of the clickthrough (stub DAG → DB query → Metabase → AI report), the
  M8 milestone artifact. (c) **Make the repo public** (`gh repo edit --visibility public`) — but
  gate this behind P0-3 and a `security-reviewer` pass (a Claude Code agent configuration used
  during development — see [`.claude/agents/`](../.claude/agents/README.md)).
- **Status:** Complete — `README.md`'s Architecture section is a real Mermaid flowchart (not
  ASCII), two demo GIFs exist (`docs/media/demo.gif`, `docs/assets/metabase-dashboard-demo.gif`),
  and the repo is public (confirmed via `gh repo view`).
- **Why it matters:** A private repo with no diagram/GIF is invisible in a job hunt; a public one
  with real numbers and a 3-minute demo is the whole point of a portfolio project.
- **Effort:** M · **Depends on:** P0-3 (real numbers) + a security review before flipping to public.

---

## P2 — Multi-omic modality: MiXCR immune-repertoire path (on-target)

### P2-1 · Add an immune-repertoire (AIRR) branch reusing the existing spine
- **What:** Add a **second assay** as a Phase-2 branch: an MiXCR-based immune-repertoire (TCR/BCR)
  path that reuses everything already built — the provenance stamp, insert-only/DynamoDB metadata
  model, Metabase dashboard, guardrailed AI summary, and GA4GH content-id primitive — but swaps the
  germline-SNV core (fastp→bwa-mem2→HaplotypeCaller→hap.py) for a repertoire core
  (QC → MiXCR align/assemble → clonotype table + repertoire metrics: clonality, diversity, top
  clones). Its "validation" analog is a reference/synthetic repertoire concordance check rather than
  hap.py-vs-GIAB. Gate it behind a new `--assay {snv,airr}` selector and a new module group
  (`pipeline/modules/repertoire/`); keep the export contract (`metrics.json` shape + provenance)
  identical so the DB/dashboard/AI layers consume it unchanged.
- **Why it matters:** Directly proves the **"assay-agnostic spine"** claim and maps 1:1 onto
  **MiLaboratories / MiXCR** — turning a generic genomics portfolio into one that speaks the target
  employer's exact stack. The strong-signal framing is: "the platform is the reusable part; the
  assay is a plug-in," demonstrated by a second modality landing on the same rails.
- **Effort:** L · **Depends on:** P0-3 and P1-1 (finish and validate the SNV path first, so "reuse
  the spine" is a demonstrated fact, not an aspiration). Record the decision as a new ADR
  (the next free number — ADR-0013 has since been used for QC warnings) when starting.

---

## AI — AI & ML depth (measure the AI, then deepen it)

The repo already ships a lot of AI (QLoRA report model, ReAct variant-interpretation agent,
RAG, triage agent, LLM healer, FHIR intake, guardrails). The gap is not *more* LLM wiring — it is
**measuring** the AI the way hap.py measures the caller, grounding it in **real annotation**, and
showing the **genomics-specific ML** a 2026 bioinformatician is expected to know. Every item below
keeps the non-negotiables: AI output passes `enforce_guardrails()`, the report model sees only
`metrics.json`, results carry provenance, and scope-widening choices get a new ADR (next free: 0037).

### Tier 1 — highest value, reinforces the "validated & traceable" story

#### AI-1 · Agent evaluation harness (the "hap.py for the LLM") ✅ Done ([#92](https://github.com/qclayssen/clinical-genomics-platform/pull/92), [ADR-0032](adr/0032-agent-evaluation-harness.md))
- **What:** A gold set of ~50–100 chr20 variants with **expert-panel-reviewed** ClinVar
  classifications (≥ 3 stars). Score the ReAct agent's ACMG call against it: accuracy, confusion
  matrix per class, hallucinated-citation rate, and tool-grounding (every claim traceable to a tool
  result). Optional LLM-as-judge for summary *wording* only, never for the classification. Wire a
  thresholded check into CI (deterministic backend in CI; real-model runs recorded as evidence).
- **Why it matters:** The strongest AI signal a clinical-genomics reviewer can see — you
  *evaluate* AI rather than just call it. Mirrors the SNV F1 ≥ 0.99 acceptance gate.
- **Effort:** M · **Depends on:** nothing.
- **Outcome:** gold n = 10 (the committed KB has only 15 ClinVar records — growing it needs a real
  ClinVar download); deterministic baseline 3-class 0.90, 0 hallucinated citations, grounding 1.0.
  Its first run found and fixed an ungrounded default `PM2`. Grounding means *traceable to a tool*,
  not *ACMG-correct* — the PS1/PP5 double-count is a documented open limitation.

#### AI-2 · Variant annotation module: VEP + AI pathogenicity scores
- **What:** `pipeline/modules/annotate/vep.nf` (one process, `stub:`, digest-pinned container)
  with AlphaMissense, SpliceAI, REVEL and CADD plugins; add a `query_annotation` tool to the agent
  so ACMG PP3/BP4 use real in-silico evidence instead of ClinVar/gnomAD lookups alone.
- **Why it matters:** AlphaMissense and SpliceAI are the deep-learning models clinical labs
  actually use; annotation is a core pipeline stage the platform currently skips.
- **Effort:** M · **Depends on:** P1-1. Annotation does not change calling, so it does not
  re-trigger hap.py — but record the plugin/cache versions in provenance.

#### AI-3 · Experiment tracking + model registry for the QLoRA model ✅ Done ([#91](https://github.com/qclayssen/clinical-genomics-platform/pull/91), [ADR-0035](adr/0035-mlflow-local-tracking-model-registry.md))
- **What:** MLflow (local file store, no server needed) logging `train_smoke.py`/`train_lora.py`
  runs with git SHA, dataset hash, base-model id and hyperparameters as tags; register the adapter
  and reference the registered version from `MODEL_CARD.md`.
- **Why it matters:** Extends the provenance rule to model artifacts; standard MLOps literacy.
- **Effort:** S · **Depends on:** nothing.

### Tier 2 — modern genomics ML (interview-relevant)

#### AI-4 · Genomic foundation-model variant scoring
- **What:** Score chr20 missense variants with a small ESM-2 (protein LM, CPU-feasible) —
  optionally a regulatory-variant model (Nucleotide Transformer / Evo 2) — and report AUROC
  against ClinVar labels, side by side with AlphaMissense from AI-2.
- **Why it matters:** Demonstrates hands-on use of foundation models with an honest, measured
  result rather than a claim.
- **Effort:** M · **Depends on:** AI-2 (for the comparison baseline).

#### AI-5 · Explainable ML variant filter, validated by hap.py
- **What:** Gradient-boosted classifier over VCF INFO/FORMAT features (VQSR/CNN-style) with SHAP
  explanations; accept it only if re-running hap.py shows SNV F1 does not regress (≥ 0.99).
- **Why it matters:** Ties ML directly to the validation spine — filtering changes re-trigger
  validation, exactly as the design rules require.
- **Effort:** M · **Depends on:** P0-3. New ADR (a filtering change).

#### AI-6 · Structural variants & CNVs (Manta + CNVkit, Truvari vs GIAB SV)
- **What:** SV/CNV calling benchmarked against the GIAB HG002 SV truth set with Truvari.
- **Why it matters:** A core clinical-genomics expectation today.
- **Effort:** L · **Depends on:** P1-1. **Widens ADR-0001's SNV-only scope** — needs a
  superseding/extending ADR first; weigh against P2-1 for focus.

### Tier 3 — agent engineering

#### AI-7 · MCP server over the knowledge base and run/provenance data ✅ Done ([#90](https://github.com/qclayssen/clinical-genomics-platform/pull/90), [ADR-0033](adr/0033-mcp-server-read-only.md))
- **What:** Expose read-only tools (ClinVar/gnomAD KB, run QC, provenance) via MCP so any MCP
  client can query runs.
- **Effort:** S · **Depends on:** nothing.

#### AI-8 · LLM observability ✅ Done ([#93](https://github.com/qclayssen/clinical-genomics-platform/pull/93), [ADR-0036](adr/0036-llm-observability-agent-call-metrics.md))
- **What:** OpenTelemetry/Langfuse traces of agent steps, token cost and latency, surfaced on the
  Metabase ops dashboard.
- **Effort:** S–M · **Depends on:** AI-1 (so traces feed eval, not just logs).

#### AI-9 · Literature-RAG tool with citation guardrail
- **What:** A PubMed/LitVar lookup per variant; the guardrail rejects any PMID not present in the
  retrieved set.
- **Effort:** M · **Depends on:** AI-1 (hallucinated-citation metric measures it).

---

## P3 — Later / future direction (roadmap only, not a build)

### P3-1 · Spatial genomics — one-page roadmap ADR only ✅ Done ([#89](https://github.com/qclayssen/clinical-genomics-platform/pull/89), [ADR-0034](adr/0034-spatial-genomics-direction.md))
- **What:** Write a single forward-looking ADR
  ([`docs/adr/0034-spatial-genomics-direction.md`](adr/0034-spatial-genomics-direction.md),
  status `Proposed`) sketching how the platform *could* extend to spatial transcriptomics
  (Visium/Xenium-style) — new QC/segmentation stages, a spatial-coordinate data model, spatial
  visualization — and, crucially, **why it is deliberately not being built now**.
- **Why it matters — and why NOT to build it:** Spatial is a genuinely different domain (imaging,
  cell segmentation, new reference/QC concepts) that would **dilute focus** and threaten the "scoped
  so one person finishes it" discipline that is itself a selling point ([ADR-0001](adr/0001-scope-giab-hg002-chr20.md)).
  A one-page ADR shows range and forward vision (relevant to a broad multi-omics employer) at S
  effort, while an actual build would be an unfinished L that weakens the portfolio. Show the
  judgement to *say no on purpose*.
- **Effort:** S (ADR only) · **Depends on:** nothing. Explicitly **do not** implement.

---

## Recommended order (at a glance)

1. **P0-1, P0-2** — close the ADR governance debt (one afternoon, pure docs, stops an active
   steering-rule violation). Honestly flag the DynamoDB IAM-vs-trigger integrity regression.
2. **P0-3** — run real validation. *The keystone.* Everything credibility-bearing depends on it.
3. **P1-1, P1-2** — finish the nf-core migration (versions/lint/nf-test) and write it up.
4. **P1-3, P1-4** — number-backed resume bullets, diagram + GIF, then go public (after a security
   review).
5. **P2-1** — the MiXCR immune-repertoire branch: prove the assay-agnostic spine (the standout,
   on-target differentiator).
6. **AI-1, AI-3, AI-7, AI-8** ✅ done — measure the agent, track the model, expose data over MCP,
   observe LLM calls. Next: **AI-2** (VEP + AlphaMissense/SpliceAI), then AI-4/AI-5/AI-9 (AI-6 only
   after its ADR). Can run in parallel with P2-1.
7. **P3-1** ✅ done — spatial genomics as a *roadmap ADR only*; a deliberate, documented "not now."

---

## Suggested task board

| ID | Item | Phase | Effort | Depends on | Owner-lane |
|---|---|---|---|---|---|
| P0-1 | ~~ADR-0011 supersedes ADR-0004 (Batch → serverless)~~ ✅ Done | P0 | S | — | documentation-writer |
| P0-2 | ~~ADR-0012 supersedes ADR-0005 (Postgres → DynamoDB); flag IAM-vs-trigger integrity nuance~~ ✅ Done | P0 | S | — | documentation-writer |
| P0-3 | ~~**Run real GIAB HG002 chr20; fill VALIDATION.md + README**~~ ✅ Done | P0 | M | Docker on machine | pipeline-engineer |
| P1-1 | Pipeline finalize: real versions.yml collation, clean `nf-core lint`, add `nf-test` | P1 | M | P0-3 | pipeline-engineer + test-engineer |
| P1-2 | Write `docs/NEXTFLOW-MIGRATION.md` (strict-DSL fixes + P1-1) | P1 | S | P1-1 | documentation-writer |
| P1-3 | Resume bullets backed by measured numbers | P1 | S | P0-3 | — |
| P1-4 | ~~README diagram + demo GIF; make repo public (after security review)~~ ✅ Done | P1 | M | P0-3, security-reviewer | documentation-writer + security-reviewer |
| P2-1 | MiXCR immune-repertoire (AIRR) branch reusing the spine; new ADR (next free number) | P2 | L | P0-3, P1-1 | pipeline-engineer |
| AI-1 | ~~Agent eval harness: ClinVar gold set, ACMG accuracy, citation/grounding metrics, CI gate~~ ✅ Done (#92) | AI | M | — | test-engineer + validation-reviewer |
| AI-2 | VEP annotate module (AlphaMissense, SpliceAI, REVEL, CADD) + `query_annotation` agent tool | AI | M | P1-1 | pipeline-engineer |
| AI-3 | ~~MLflow tracking + model registry for the QLoRA adapter~~ ✅ Done (#91) | AI | S | — | — |
| AI-4 | Foundation-model (ESM-2) variant scoring, AUROC vs ClinVar | AI | M | AI-2 | — |
| AI-5 | Explainable ML variant filter (GBM + SHAP), gated on hap.py F1 ≥ 0.99; new ADR | AI | M | P0-3 | pipeline-engineer + validation-reviewer |
| AI-6 | SV/CNV calling (Manta, CNVkit) + Truvari vs GIAB SV; ADR widening ADR-0001 | AI | L | P1-1, ADR | pipeline-engineer |
| AI-7 | ~~MCP server over KB + run/provenance data~~ ✅ Done (#90) | AI | S | — | — |
| AI-8 | ~~LLM observability (traces, cost, latency → Metabase)~~ ✅ Done (#93) | AI | S–M | AI-1 | — |
| AI-9 | Literature-RAG (PubMed/LitVar) with PMID citation guardrail | AI | M | AI-1 | — |
| P3-1 | ~~Spatial genomics roadmap ADR only (Proposed; do not build)~~ ✅ Done (#89) | P3 | S | — | documentation-writer |
