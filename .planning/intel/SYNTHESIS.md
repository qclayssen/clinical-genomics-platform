# Synthesis Summary

Entry point for downstream consumers (`gsd-roadmapper`). Produced by `gsd-doc-synthesizer`
over the complete classification set. This is a **re-run** that overwrites a prior pass which
covered only ADRs 0001-0012; ADRs 0013, 0014, 0015 and 0016 are now included.

Mode: `new` — no existing PROJECT.md, ROADMAP.md, REQUIREMENTS.md or STATE.md.
Precedence: ADR > SPEC > PRD > DOC, with per-doc override 0 on ADRs 0013-0016.

---

## Doc counts by type

| Type | Count |
|---|---|
| ADR | 16 |
| SPEC | 3 |
| DOC | 17 |
| PRD | 0 |
| UNKNOWN | 0 |
| **Total** | **36** |

All 36 classified at `confidence: high`; 35 of 36 with `manifest_override: true`.

## Decisions

14 locked, 2 superseded. Detail in `decisions.md`.

**Locked (authoritative):**
- ADR-0001 — scope: GIAB HG002/NA24385, chr20, germline SNVs only · `docs/adr/0001-scope-giab-hg002-chr20.md`
- ADR-0002 — Nextflow DSL2, nf-core conventions · `docs/adr/0002-nextflow-dsl2-pipeline.md`
- ADR-0003 — truth-set benchmarking as a first-class stage; **SNV F1 >= 0.99** acceptance criterion (engine choice only superseded by ADR-0015) · `docs/adr/0003-truth-set-validation.md`
- ADR-0006 — Metabase ops dashboard from committed SQL over `v_run_summary` · `docs/adr/0006-metabase-dashboard.md`
- ADR-0007 — QLoRA fine-tune of a <=3B open model, with CPU smoke test and offline fallback · `docs/adr/0007-qlora-small-open-model.md`
- ADR-0008 — `enforce_guardrails()` in code, human-in-the-loop sign-off · `docs/adr/0008-guardrails-human-in-the-loop.md`
- ADR-0009 — per-step containers pinned by sha256 digest · `docs/adr/0009-docker-pinned-by-digest.md`
- ADR-0010 — incremental GA4GH alignment; `sha512t24u` implemented · `docs/adr/0010-ga4gh-standards-alignment.md`
- ADR-0011 — serverless compute: Step Functions + 7 Lambdas + EventBridge, free-tier, $0 idle · `docs/adr/0011-serverless-lambda-stepfunctions.md`
- ADR-0012 — DynamoDB primary metadata store, Postgres as Metabase read-replica · `docs/adr/0012-dynamodb-primary-store.md`
- ADR-0013 — QC warnings, adaptive mean±2σ thresholds, multi-level self-healing, notify-then-auto-execute · `docs/adr/0013-qc-warnings-adaptive-thresholds-self-healing.md`
- ADR-0014 — agentic ACMG/AMP variant interpretation via a ReAct loop with deterministic fallback · `docs/adr/0014-agentic-variant-interpretation.md`
- ADR-0015 — hap.py **xcmp** engine, not vcfeval · `docs/adr/0015-happy-xcmp-engine-not-vcfeval.md`
- ADR-0016 — three-tier CI/CD; DB migration + immutability tests machine-verified and blocking; 6+ status checks per PR · `docs/adr/0016-cicd-strategy.md`

**Superseded (retained for provenance, not authoritative):**
- ADR-0004 — Batch/Fargate compute superseded by ADR-0011. **PARTIAL**: its CDK/IaC, S3
  data-lake, scoped-IAM and Jest guardrail-test decisions remain authoritative.
- ADR-0005 — insert-only Postgres as primary store superseded by ADR-0012. The "amend, never
  erase" semantic survives; the trigger-level immutability guarantee does not.

## Requirements

19 extracted — 15 from the EARS SPEC, 4 introduced by locked ADRs postdating it. Detail in
`requirements.md`. No PRDs exist, so no requirement has competing acceptance variants.

From `.kiro/specs/clinical-genomics-platform/requirements.md`:
REQ-pipeline-execution, REQ-serverless-orchestration, REQ-eventbridge-automation,
REQ-s3-data-lake, REQ-dynamodb-metadata-store, REQ-observability, REQ-iam-least-privilege,
REQ-metabase-dashboard, REQ-rag-reporting, REQ-lora-finetuning, REQ-provenance-audit,
REQ-docker-containerization, REQ-cicd, REQ-cost-guardrails, REQ-production-migration-docs.

ADR-derived (postdate the SPEC, authoritative where they overlap):
REQ-qc-warnings-self-healing (ADR-0013), REQ-variant-interpretation (ADR-0014),
REQ-validation-engine-xcmp (ADR-0015), REQ-cicd-tiers (ADR-0016).

## Constraints

15 extracted from the three SPEC documents. Detail in `constraints.md`.

| Type | Count | Entries |
|---|---|---|
| architecture | 2 | C-arch-cdk-stacks, C-arch-implementation-status |
| schema | 3 | C-data-dynamodb-single-table, C-data-s3-prefixes, C-data-provenance-stamp |
| nfr | 7 | C-nfr-freetier, C-nfr-retry-semantics, C-nfr-containers, C-nfr-testing, C-nfr-ci-permissions, C-nfr-caller-selection, C-nfr-validation-acceptance |
| protocol | 2 | C-protocol-eventbridge, C-protocol-audit-records |
| api-contract | 2 | C-contract-guardrails, C-contract-rag-retrieval |

## Context

9 topics from 17 DOC sources. Detail in `context.md`: project identity and honesty posture;
validation evidence; how to run the platform; standards alignment; architecture evolution and
migration; build status and planning; governance conventions; known documentation drift.

## Conflicts

**0 blockers · 4 warnings · 0 competing variants · 13 auto-resolved (INFO)**

Full report: `.planning/INGEST-CONFLICTS.md`

Warnings requiring a decision before routing:
- **W1** — no built cloud execution substrate for real genomics compute. Re-assessed against
  the complete set: NOT resolved by ADRs 0013-0016. It is an acknowledged limitation declared
  by ADR-0011 itself, not a hidden document conflict, but it still has no built remedy.
- **W2** — the ADR-0013 healer Lambda's Ollama runtime is unplaced against the 512 MB / 15 min
  free-tier Lambda envelope.
- **W3** — measured validation covers chr20:1,000,000-2,000,000 (1 Mb), narrower than
  ADR-0001's locked full-chr20 scope.
- **W4** — ADR-0016's blocking immutability-trigger tests prove the demoted Postgres replica;
  the DynamoDB primary's IAM-based append-only control has no equivalent machine-verified check.

Notable resolutions carried into the intel:
- The prior pass's vcfeval/xcmp stale-engine warning is **RESOLVED**. ADR-0015 is now in the
  set; the final locked decision records **xcmp** as the engine while ADR-0003's SNV F1 >= 0.99
  acceptance criterion and truth-set methodology remain authoritative. `docs/VALIDATION.md`
  already states xcmp, so no documentation drift remains on this point.
- ADR-0005 -> ADR-0012 and ADR-0004 -> ADR-0011 (partial) supersessions auto-resolved, not
  blockers.
- Reciprocal supersedes/superseded-by backlinks produce 2-node reference cycles by design; this
  is the project's required append-only ADR convention, so they are recorded as INFO. Six
  cycles found, all benign; max traversal depth 3 of a 50 cap; no document excluded from
  synthesis.

## Per-type intel files

- `.planning/intel/decisions.md` — 16 ADR entries with locked/superseded status and scope
- `.planning/intel/requirements.md` — 19 requirements with acceptance criteria and ADR overlays
- `.planning/intel/constraints.md` — 15 constraints by type, with ADR overrides marked inline
- `.planning/intel/context.md` — DOC notes by topic, including documentation drift
- `.planning/INGEST-CONFLICTS.md` — three-bucket conflict report
