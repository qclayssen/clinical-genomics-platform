# ADR-0018 — Execution substrate matrix and healer LLM runtime placement

**Status:** Accepted · **Date:** 2026-07-25 · **Affirms:** [ADR-0017](0017-local-nextflow-sole-real-compute.md) · **Supersedes:** the "runs unchanged on AWS Batch" aside in [ADR-0002](0002-nextflow-dsl2-pipeline.md) §Consequences

## Decision

1. **Local Nextflow + Docker is the only substrate on which this repo runs real genomics compute.** This affirms ADR-0017. No cloud execution substrate is provisioned, and none will be added without a superseding ADR that also amends REQ-cost-guardrails.
2. **The `aws` Nextflow profile is metadata-and-storage only.** It publishes results to S3 and records metadata in DynamoDB. It MUST NOT set `executor = 'awsbatch'`. The `CGP_BATCH_QUEUE` variable is removed.
3. **The healer Lambda's LLM runtime is: none in the cloud.** The deployed healer path is `rule_based_classify()` only. The Ollama client is a local/dev affordance and is **opt-in via an explicit endpoint** — there is no default endpoint, and the deployed Lambda never attempts a network call to an LLM.
4. **Enforced by test, not by prose.** A unit test fails if the healer's default path requires an in-Lambda or localhost LLM server; a CDK test fails if any Lambda is given a localhost LLM endpoint; a CI grep fails if a Nextflow config reintroduces a cloud executor.

## Context

ADR-0011 moved compute off Batch/Fargate to reach $0 idle. ADR-0017 named local Nextflow as the sole real-compute path. Neither ADR recorded the full option matrix, so a reviewer cannot see what was priced and rejected. Three concrete contradictions remain in the repo:

- `pipeline/conf/aws.config:15` sets `executor = 'awsbatch'` — a working cloud-execution path that contradicts ADR-0017 and REQ-cost-guardrails, invisible to the CDK guardrail tests because they only scan synthesized CloudFormation.
- `lambdas/healer/handler.py:138` defaults `OLLAMA_URL` to `http://localhost:11434`. A 512 MB Lambda has no such server; every deployed invocation pays a 30 s socket timeout before falling back.
- `infra/lib/orchestration-stack.ts` never deploys the healer at all — `EscalateToHealer` is an `sfn.Pass` (line 247). The healer is local/test-only code today.

Sizing note that makes local viable: the pipeline targets a **chr20-only reference** (`pipeline/nextflow.config:20`, `assets/reference/GRCh38_chr20.fa`, ~64 Mbp). bwa-mem2 index and peak RSS are a few GB, not the ~35–40 GB a whole-genome index demands. `hap.py` on chr20 is comfortable in the 8 GB `process_medium` label. A 16 GB developer laptop is sufficient hardware for the full Phase 3 validation run.

## Options considered

Cost signals assume demo scale: one HG002 chr20 run every few days, idle otherwise.

### (A) Local-only, researcher-run — **CHOSEN**

Operator runs `nextflow run main.nf -profile docker` on their own machine. Cloud records metadata only.

| | |
|---|---|
| **Pros** | $0 cloud; no guardrail violations; zero new infra; already working today; reproducible via pinned digests (ADR-0009); honest about scope |
| **Cons** | No one-click cloud run; validation evidence depends on operator hardware + 11 GB staged BAM; no multi-tenant story |
| **Ops complexity** | **Low** — already built |
| **Cost** | **$0** (uses existing hardware) |
| **Guardrails** | None violated |
| **Runs hap.py / Phase 3?** | **Yes** — chr20 at 8 GB / 4 cores |

### (B) Cloud-managed batch — AWS Batch / ECS / Fargate

Nextflow `awsbatch` executor against a managed compute environment in a VPC.

| | |
|---|---|
| **Pros** | Real cloud execution; scales past one machine; `-profile aws` already sketched |
| **Cons** | Needs VPC + NAT (~$32/mo standing, not free-tier); Fargate per-run cost; adds a VPC/SG/ECR surface to secure and review; kills the "leave it deployed as a live demo" property |
| **Ops complexity** | **High** — VPC, subnets, NAT, job queues, compute env, ECR, IAM job roles |
| **Cost** | **Medium–High** — ~$32/mo idle + per-run vCPU/GB |
| **Guardrails** | **VIOLATES REQ-cost-guardrails** (`AWS::Batch::*`, `AWS::ECS::Service`, `AWS::EC2::NatGateway` all banned by `infra/test/stacks.test.ts` §2 and `.github/workflows/infra-ci.yml`); violates ADR-0011 |
| **Runs hap.py / Phase 3?** | Yes |

### (C) HealthOmics / managed genomics service

Upload `main.nf` as a HealthOmics private workflow; Step Functions calls `StartRun`.

| | |
|---|---|
| **Pros** | The architecturally *correct* production answer; managed Nextflow runtime; no 15-min limit; HIPAA-eligible; zero pipeline code change (already documented in `docs/PRODUCTION-MIGRATION.md` §1) |
| **Cons** | Not free-tier: ~$0.50/GB-mo sequence store + per-run compute; requires an AWS account with real spend; regional availability constraints; a second execution path to keep validated |
| **Ops complexity** | **Medium** — workflow packaging, sequence/reference stores, IAM service role |
| **Cost** | **Medium–High** — ~$50–500/mo depending on volume |
| **Guardrails** | Violates the free-tier requirement (`.kiro/specs/.../requirements.md` §14.3); would require amending REQ-cost-guardrails in the same change |
| **Runs hap.py / Phase 3?** | Yes |
| **Status** | **Retained as the documented production migration path — not deployed.** |

### (D) Hybrid: local + cloud burst

Lambda/Step Functions triggers a local Nextflow run via webhook, tunnel, or SSM agent.

| | |
|---|---|
| **Pros** | Keeps $0 idle while making the cloud console appear to drive real runs |
| **Cons** | Needs an inbound endpoint into a developer machine (tunnel, ngrok, or SSM hybrid activation); fragile and offline whenever the laptop is; a genuine security liability — an internet-reachable trigger for local shell execution; demo value is theatre, not architecture |
| **Ops complexity** | **High** — tunnel lifecycle, auth, retry semantics, split failure domains |
| **Cost** | **Low** ($0–5/mo) but with a high *risk* cost |
| **Guardrails** | No CloudFormation violation, but contradicts the "no unbypassable trust boundaries" posture; ADR-0017 already rejected it |
| **Runs hap.py / Phase 3?** | Yes, but only when the laptop is up |

### (E) Dedicated EC2 / EKS cluster

A persistent instance (or EKS node group) with Nextflow + Docker; `-profile local` on a cloud host.

| | |
|---|---|
| **Pros** | Real cloud execution with no VPC/NAT if placed in a public subnet; full tool control; spot pricing is cheap per-run |
| **Cons** | An instance sized for alignment (≥8 GB) is **not** in the free tier — t2/t3.micro's 1 GB cannot run bwa-mem2 or DeepVariant (the demo host already had to move to t3.small for Metabase alone, commit `c742f48`); patching, SSH surface, and idle cost are all now yours; EKS adds a flat ~$73/mo control-plane charge |
| **Ops complexity** | **Medium** (EC2) / **High** (EKS) — AMI, patching, storage, teardown discipline |
| **Cost** | **Medium** (EC2 on-demand ~$25–60/mo if left up; ~$0.03/hr spot) / **High** (EKS ≥$73/mo) |
| **Guardrails** | EKS violates cost guardrails outright; a persistent EC2 breaks $0-idle unless stopped between runs; both violate the free-tier claim |
| **Runs hap.py / Phase 3?** | Yes |

## Why (A)

- **It is the only option that costs nothing and violates no guardrail.** Every alternative requires either amending REQ-cost-guardrails or accepting standing spend on a portfolio project.
- **The scope makes it sufficient.** chr20 on GRCh38 (ADR-0001) fits in a laptop's RAM. The compute this project needs is not the compute that justifies a cluster.
- **The hard parts are already in the cloud.** Provenance, append-only metadata, least-privilege IAM, event-driven orchestration and guardrailed AI are what a reviewer should judge — and those all run on AWS today. Moving alignment to Batch would demonstrate nothing new and would delete the $0-idle property that lets the demo stay live.
- **The production answer is already written down.** Option (C) is documented in `docs/PRODUCTION-MIGRATION.md` with a cost table. Naming the correct production path while honestly stating it is not deployed is stronger evidence of judgement than deploying a half-scaled version of it.

## Rejected

- **(B) Batch/ECS/Fargate** — NAT gateway idle cost breaks $0-idle; explicitly banned by the guardrail tests. Already rejected by ADR-0011; this ADR additionally removes the residual `awsbatch` executor from `pipeline/conf/aws.config`.
- **(C) HealthOmics** — correct but not free-tier. Kept as the documented migration path.
- **(D) Hybrid burst** — inbound trigger into a developer machine is a security cost with no architectural payoff.
- **(E) EC2/EKS** — free-tier instance sizes cannot run the tools; anything that can, costs money while idle.

## Healer LLM runtime

**Question:** can a healer LLM run inside a 512 MB Lambda? **No.**

| Approach | Verdict |
|---|---|
| **In-Lambda Ollama** | **Infeasible.** Ollama is a server process, not a library — it must be running before `_call_ollama` connects, and Lambda gives no way to start one alongside the handler. Even setting that aside: the smallest useful weights (llama3.2:3b, Q4) are ~2 GB versus a 512 MB memory ceiling and a 250 MB unzipped package limit (10 GB via container image, still over budget on RAM); cold-start model load blows the 15-min wall clock; and there is no GPU. The current `http://localhost:11434` default is unreachable by construction and merely buys a 30 s timeout on every deployed invocation. |
| **External self-hosted Ollama** | Feasible but needs a persistent host — ECS/Fargate or EC2, i.e. option (B) or (E). **Violates REQ-cost-guardrails / free-tier.** Rejected for the deployed path; retained as the *local dev* configuration via an explicitly-set `OLLAMA_URL`. |
| **Quantized small LLM inside 512 MB** | Technically possible (a ~100–200 M-param Q4 model plus `llama.cpp` bindings can fit), but a model that small cannot reliably emit constrained JSON over a 6-action set. It would be *less* accurate than `rule_based_classify()`, which already resolves OOM/timeout/QC/hard-fail patterns deterministically at 0.75–0.85 confidence. Adding a weak LLM to replace working rules is a net regression in both accuracy and auditability. **Rejected.** |
| **Remote API (Bedrock / Anthropic / OpenAI)** | Technically the cleanest fit for Lambda — no local runtime, ~50 MB SDK. But: Bedrock is banned by REQ-cost-guardrails; a third-party API means a per-token bill, an API key in Secrets Manager, and *pipeline failure context leaving the account*. Failure causes may embed sample IDs and file paths. Provenance also suffers — a hosted model version is not pinnable the way a container digest is (ADR-0009), so a healer decision could not be reproduced from its stamp. **Rejected for the deployed path.** |

**Decision:** the deployed healer is **deterministic-only**. `rule_based_classify()` is the production path, not a fallback. The Ollama client remains for local development and is **opt-in**: `OLLAMA_URL` gets no default, and when it is unset `_call_ollama` returns `None` without attempting a network call. The healer Lambda, if it is ever deployed (it is currently an `sfn.Pass`), is 256 MB / 30 s and is granted no egress-dependent permissions.

**Test requirement (binding):** a test MUST fail if the healer's deployed path requires an in-Lambda or localhost LLM server. Specifically — with a clean environment, `handler()` returns `source == "rule_based"` and makes **zero** network calls; and no synthesized Lambda carries an LLM endpoint env var pointing at `localhost` or `127.0.0.1`.

## Consequences

**Good**
- One answer to "where does compute run", with the priced alternatives visible.
- The `-profile aws` contradiction is removed; `docs/usage.md:64` becomes true.
- Deployed healer invocations stop paying a 30 s timeout and become fully deterministic — which is also the better answer for an auditable clinical-adjacent system.
- Guardrail coverage extends beyond CloudFormation to Nextflow configs and healer config.

**Bad / accepted**
- No cloud "run my sample" button. Stated plainly in README, SOP and this ADR.
- Phase 3 validation requires local Nextflow + Docker + the staged 11 GB BAM. If that run cannot be completed, the honest outcome is a scope-narrowing ADR, never a placeholder number.
- The healer's LLM path is exercised only in local dev and in mocked tests. Its cloud behaviour is rules-only, and the ADR says so rather than implying AI is in the loop.
- `-profile aws` is now a partial profile (storage/metadata, not execution). Its comment header must say so to avoid re-confusing the next reader.

## Next steps

1. Remove `executor`/`queue`/`workDir` cloud-execution settings from `pipeline/conf/aws.config`.
2. Remove the `http://localhost:11434` default from `lambdas/healer/handler.py`.
3. Add the healer no-localhost test and the CDK no-localhost-endpoint test.
4. Add a CI guard that fails on a cloud executor in any `pipeline/**/*.config`.
5. Align `docs/FOR-RECRUITERS.md`, `docs/GLOSSARY.md`, `docs/adr/README.md`, `CLAUDE.md`.
6. Mark EXEC-01 / EXEC-02 / EXEC-03 satisfied in `.planning/REQUIREMENTS.md` and refresh `.planning/STATE.md` (W1, W2 closed).
