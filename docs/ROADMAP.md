# Roadmap — rest of the project

An honest, prioritized next-steps plan for the **non-serverless** parts of the platform.
Phases run **P0 (do now) → P3 (later)**. Each item lists *what*, *why it matters for the job
hunt*, rough *effort* (S ≈ hours, M ≈ 1–2 days, L ≈ a week+), and *dependencies*.

Tone note: this repo's credibility comes from *not overclaiming*. Every item below either
produces measured evidence or closes a gap between what the docs say and what the code does.
Nothing here invents a new capability to look impressive.

> **Single highest-ROI next action:** run the pipeline on real GIAB HG002 chr20 and replace the
> `_fill_` placeholders in [`docs/VALIDATION.md`](VALIDATION.md) (item **P0-3**). It is the one
> action that converts the whole project from "scaffolded" to "measured", and it unblocks the
> resume bullets and going public. Do the two ADR fixes (P0-1, P0-2) first only because they are
> an afternoon of pure docs and close an active steering-rule violation.

---

## Owned by Kiro spec (not tracked here)

The **serverless infrastructure migration** (Lambda + Step Functions + DynamoDB) and the
**RAG reporter** (FAISS + Ollama) are owned by the Kiro spec and tracked in
[`.kiro/specs/clinical-genomics-platform/tasks.md`](../.kiro/specs/clinical-genomics-platform/tasks.md).
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

### P0-1 · ADR-0011: supersede ADR-0004 (Batch/Fargate → serverless)
- **What:** Write `docs/adr/0011-serverless-lambda-stepfunctions.md`. Status `Accepted`; record
  the decision to move compute from AWS Batch/Fargate to Lambda + Step Functions + EventBridge.
  Set [ADR-0004](adr/0004-aws-cdk-batch-fargate.md) status to `Superseded by ADR-0011` and add
  ADR-0011 to the index table in [`docs/adr/README.md`](adr/README.md) (currently stops at 0010).
- **Why it matters:** [CLAUDE.md](../CLAUDE.md) makes ADRs a non-negotiable rule — "supersede it
  and update its status; never silently edit history." The serverless pivot has already landed in
  `infra/` and `lambdas/` with **no superseding ADR**, so the repo is currently violating its own
  governance rule. For a role screening on engineering judgement, an *unrecorded* architecture
  reversal is worse than the reversal itself. Fixing it demonstrates the discipline the project
  claims to have.
- **Effort:** S · **Depends on:** nothing (pure docs; the code change is Kiro's).

### P0-2 · ADR-0012: supersede ADR-0005 (insert-only Postgres → DynamoDB primary)
- **What:** Write `docs/adr/0012-dynamodb-primary-metadata-store.md`. Status `Accepted`; DynamoDB
  single-table becomes the primary metadata store, Postgres becomes a Metabase read-bridge fed by
  the DynamoDB→Postgres sync. Set [ADR-0005](adr/0005-insert-only-postgres.md) to
  `Superseded by ADR-0012`; update the index.
- **Why it matters — flag the integrity nuance honestly:** ADR-0005's whole selling point was
  **tamper-evidence enforced at the database level** by `forbid_mutation()` triggers
  (`db/schema.sql`) that reject UPDATE/DELETE. DynamoDB append-only is instead enforced by
  **IAM explicit-DENY** on `dynamodb:DeleteItem`/`UpdateItem` in the per-Lambda roles. This is a
  **weaker, different** boundary: an actor with IAM-policy-edit rights can lift the DENY, whereas
  the Postgres trigger lives inside the data engine. ADR-0012 must state this trade-off plainly
  (append-only is now a *policy* control, not a *data-layer* control) rather than pretending the
  guarantee is unchanged. Note the mitigation: the roles also DENY `iam:PutRolePolicy` /
  `AttachRolePolicy` on themselves. A reviewer will respect the project far more for naming this
  regression than for glossing it.
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
     with `collectFile` (a raw concat, to keep the stub DAG at nine tasks). Replace with a proper
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

### P1-2 · Document the Nextflow migration issues
- **What:** Create `docs/NEXTFLOW-MIGRATION.md` capturing the strict-DSL / Nextflow 26.04
  compatibility fixes. The raw material already exists in [`docs/END-TO-END.md`](END-TO-END.md)
  ("Fixes made to get here": `check_max()` → `resourceLimits`, provenance block moved inside
  `workflow {}`, `publishDir` closure form, stub CI profile change) — promote it into a standalone
  migration note and extend it with the P1-1 changes (versions collation, lint, nf-test).
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

### P1-4 · Portfolio polish — architecture diagram + demo GIF, then go public
- **What:** (a) Replace the ASCII architecture block in [`README.md`](../README.md) with a rendered
  diagram (and update it for the serverless topology once Kiro's migration settles). (b) Record a
  ~3-minute demo GIF/clip of the clickthrough (stub DAG → DB query → Metabase → AI report), the
  M8 milestone artifact. (c) **Make the repo public** (`gh repo edit --visibility public`) — but
  gate this behind P0-3 and a `security-reviewer` pass, per
  [`.claude/agents/README.md`](../.claude/agents/README.md).
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
  (ADR-0013) when starting.

---

## P3 — Later / future direction (roadmap only, not a build)

### P3-1 · Spatial genomics — one-page roadmap ADR only
- **What:** Write a single forward-looking ADR (e.g. `docs/adr/0014-spatial-genomics-direction.md`,
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
6. **P3-1** — spatial genomics as a *roadmap ADR only*; a deliberate, documented "not now."

---

## Suggested task board

| ID | Item | Phase | Effort | Depends on | Owner-lane |
|---|---|---|---|---|---|
| P0-1 | ADR-0011 supersedes ADR-0004 (Batch → serverless) | P0 | S | — | documentation-writer |
| P0-2 | ADR-0012 supersedes ADR-0005 (Postgres → DynamoDB); flag IAM-vs-trigger integrity nuance | P0 | S | — | documentation-writer |
| P0-3 | **Run real GIAB HG002 chr20; fill VALIDATION.md + README (highest ROI)** | P0 | M | Docker on machine | pipeline-engineer |
| P1-1 | Pipeline finalize: real versions.yml collation, clean `nf-core lint`, add `nf-test` | P1 | M | P0-3 | pipeline-engineer + test-engineer |
| P1-2 | Write `docs/NEXTFLOW-MIGRATION.md` (strict-DSL fixes + P1-1) | P1 | S | P1-1 | documentation-writer |
| P1-3 | Resume bullets backed by measured numbers | P1 | S | P0-3 | — |
| P1-4 | README diagram + demo GIF; make repo public (after security review) | P1 | M | P0-3, security-reviewer | documentation-writer + security-reviewer |
| P2-1 | MiXCR immune-repertoire (AIRR) branch reusing the spine; new ADR-0013 | P2 | L | P0-3, P1-1 | pipeline-engineer |
| P3-1 | Spatial genomics roadmap ADR only (Proposed; do not build) | P3 | S | — | documentation-writer |
