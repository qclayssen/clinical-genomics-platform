# ADR-0017 — Local Nextflow is the sole real-compute path; cloud execution is orchestration-only

**Status:** Accepted · **Date:** 2026-07-24

## Context

ADR-0011 replaced AWS Batch/Fargate compute with Lambda + Step Functions orchestration to achieve $0 idle cost within AWS always-free tier. ADR-0011 §Consequences noted that "Lambda (≤512 MB, ≤15 min, no GPU) cannot run real genomics tools" but left the ultimate execution substrate ambiguous — some docs referenced AWS Batch as still-deployable, others implied HealthOmics was the cloud path, and the healer Lambda referenced `http://localhost:11434` (Ollama) which cannot exist in a 512 MB Lambda environment.

Three substrate options were evaluated:

| Option | Real Compute | Cloud Orchestration | Cost | Consequence |
|--------|--------------|---------------------|------|-------------|
| **(a) Local Nextflow** | Local Docker | Lambda + SFN (metadata only) | $0 | Honest demo-scale limitation |
| (b) HealthOmics | HealthOmics private workflows | HealthOmics + Step Functions | ~$50-500/mo | Breaks free-tier requirement |
| (c) Hybrid cloud/local | Local Docker | Lambda calls local Nextflow via webhook | $0 | Fragile; requires exposed endpoint |

Option (b) contradicts the locked free-tier requirement (§14.3 "targets AWS free-tier compliance for all deployed resources"). Option (c) adds operational complexity (NAT/tunnel/webhook) for a portfolio demo without production benefit.

The platform's design already demonstrates the correct production answer — ADR-0011 and `docs/PRODUCTION-MIGRATION.md` both cite AWS HealthOmics as the production migration path. The demo's purpose is to prove the orchestration logic, data model, and provenance patterns that production would scale, not to run cloud WGS alignment at portfolio scale.

## Decision

**Local Nextflow DSL2 pipeline with Docker containers is the sole path for real genomics compute** (BWA-MEM2 alignment, GATK HaplotypeCaller, DeepVariant, hap.py validation). The 12 nf-core-style modules in `pipeline/modules/` and the helper scripts in `pipeline/bin/` execute locally via `nextflow run main.nf -profile test,docker` or on real staged data.

**AWS Lambda + Step Functions orchestration is metadata-only**: it drives workflow state, records provenance/audit entries to DynamoDB, publishes CloudWatch metrics, and demonstrates event-driven serverless patterns. It does **not** execute bioinformatics tools and does not invoke Nextflow programmatically.

**Healer Lambda uses rule-based fallback by default**: the `lambdas/healer/handler.py` Ollama integration (lines 138-167) attempts to call a local Ollama server if `OLLAMA_URL` is configured, but falls back to deterministic rule-based classification (`rule_based_classify()`, lines 68-123) when Ollama is unavailable. In the deployed Lambda (512 MB, no Ollama server), the rule-based path is the primary code path. The Ollama integration exists to demonstrate the pattern for local/dev environments where an external Ollama instance is available.

**Production migration path remains AWS HealthOmics** (documented in `docs/PRODUCTION-MIGRATION.md` §1): the existing `main.nf` and all modules upload directly to HealthOmics private workflows, which provide managed Nextflow runtime, no timeout constraints, automatic compute scaling, and HIPAA eligibility. Cost: $50-500/month depending on volume. The demo proves the workflow logic HealthOmics would scale.

## Consequences

**Good**
- **Honest about scope**: no documentation claims cloud execution that does not exist. The demo proves orchestration, provenance, and data patterns — the parts that are hard to get right — while stating plainly that heavy compute runs locally.
- **$0 cloud cost at demo scale**: free-tier compliance maintained without compromising the demonstration of serverless orchestration, IAM least-privilege, EventBridge automation, and DynamoDB append-only patterns.
- **Production path is documented and technically sound**: HealthOmics as the cited migration path is the architecturally correct answer for serverless genomics on AWS; the demo's value is proving the surrounding patterns (metadata, audit, guardrails) that production would reuse.

**Bad / accepted limitations**
- **Real WGS compute requires local environment**: running the full pipeline end-to-end (not stub mode) needs Nextflow + Docker + staged GIAB data on the operator's machine. CI runs `-stub` mode and the ML smoke tests; measured validation numbers come from local execution documented in `docs/VALIDATION.md`.
- **Healer Lambda rule-based fallback only in deployed Lambda**: the Ollama LLM diagnostic path requires an external Ollama server (local dev, or a future ECS/Fargate service outside free-tier). The deployed 512 MB Lambda uses deterministic rules. This is documented as the expected behavior, not a limitation.
- **No "run my sample in the cloud with one button"**: this platform demonstrates clinical-grade **patterns** (traceability, validation, guardrails, self-healing), not a one-click SaaS service. Operators run the pipeline locally and the cloud infra records results. A production system using HealthOmics would close this gap.

## Alternatives considered

- **AWS HealthOmics (option b)**: the correct production architecture, but not free-tier (~$0.50/GB stored + per-run compute cost). Adopting it would require either (1) abandoning the free-tier requirement that enables the live demo, or (2) documenting it as "not deployed" — which is the outcome this ADR already provides (HealthOmics is the documented migration path, not a deployed component).
- **Hybrid: Lambda invokes local Nextflow (option c)**: requires exposing a webhook/tunnel for Lambda to call back to a local machine, or deploying Nextflow in ECS (not free-tier). Adds operational fragility for a portfolio demo. Rejected: the coupling outweighs the marginal demo benefit.
- **Keep AWS Batch references (no decision)**: rejected because it leaves three contradictory answers (Batch, HealthOmics, local) in the docs. This ADR closes that ambiguity.

## Impact on other decisions

- **Supersedes nothing**: ADR-0011 (serverless orchestration) stands; this ADR clarifies that ADR-0011's "Lambda cannot run real tools" means **local Nextflow is the compute path**, not "Batch remains an option."
- **Cost guardrails (infra test `stacks.test.ts:86-113`)**: already assert zero Batch/Fargate/NAT resources. No change needed.
- **Requirements §14.3 (free-tier compliance)**: already states Lambda + Step Functions are the cloud components; DynamoDB is the data store. Real compute being local aligns with this.
- **Production migration doc (`docs/PRODUCTION-MIGRATION.md` §1)**: already cites HealthOmics as the production path. This ADR affirms that as correct and states the demo does not deploy it.

## Validation

A reader following `docs/SOP-run-pipeline.md` §4.3 ("Execute") will find:
- **Local path**: `nextflow run main.nf -profile test,docker` — explicitly documented, runs real tools
- **AWS path**: references to "AWS Batch" removed; replaced with "cloud orchestration handles metadata; real compute runs locally"

The healer Lambda's rule-based fallback is the primary path in deployed 512 MB Lambda; Ollama integration is documented as available for local/dev environments with an external Ollama server.

Re-validation trigger (ADR-0003): this decision does not change reference, caller, or filtering — no re-validation required. It clarifies **where** the existing validated pipeline runs.
