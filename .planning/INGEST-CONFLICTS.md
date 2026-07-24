## Conflict Detection Report

Mode: new (no existing PROJECT.md / ROADMAP.md / REQUIREMENTS.md / STATE.md).
Set: 36 classified documents — 16 ADR, 3 SPEC, 17 DOC, 0 PRD, 0 UNKNOWN.
Precedence: ADR > SPEC > PRD > DOC. ADRs 0013-0016 carry per-doc precedence override 0.
This is a re-run over the complete set; it supersedes the prior pass that covered ADRs 0001-0012.

### BLOCKERS (0)

No blockers. Specifically checked and cleared:

- No LOCKED-vs-LOCKED contradiction survives. The one candidate — ADR-0003 (locked) declaring
  the vcfeval engine against ADR-0015 (locked) declaring xcmp — is not a contradiction because
  both documents declare the supersession explicitly and reciprocally. See INFO I1.
- No UNKNOWN-type or low-confidence classifications exist; all 36 are `confidence: high` and
  35 of 36 carry `manifest_override: true`.
- No reference cycle blocks synthesis. All detected cycles are benign reciprocal doc links;
  max traversal depth reached was 3, well under the 50 cap. See INFO I4.

### WARNINGS (4)

[WARNING] W1 — No built cloud execution substrate for real genomics compute
  Found: docs/adr/0011-serverless-lambda-stepfunctions.md (Accepted, LOCKED) states verbatim
    that "Lambda (<=512 MB, <=15 min, no GPU) cannot run real genomics tools (BWA-MEM2
    alignment, DeepVariant, hap.py) on real WGS data", and that heavy compute "runs via the
    local Nextflow pipeline". .kiro/specs/clinical-genomics-platform/requirements.md
    §Requirement 14.3 (REQ-cost-guardrails) forbids provisioning AWS Batch, Fargate, NAT
    Gateways or RDS, and §14.5 mandates CDK guardrail tests asserting zero such resources.
    docs/adr/0004-aws-cdk-batch-fargate.md is Superseded for compute. The complete set,
    including the four newly added ADRs, was re-checked: ADR-0013 layers QC evaluation, a
    healer Lambda and Step Functions Choice states onto the same Lambda substrate; ADR-0014 is
    a post-pipeline local interpreter; ADR-0015 is a hap.py engine change; ADR-0016 is CI/CD
    only. None of them introduces a cloud execution substrate.
  Impact: any roadmap item phrased as "run the pipeline in the cloud" or "process a sample
    end-to-end on AWS" has no substrate to land on and would be planned against a capability
    that does not exist. The only documented remedy, AWS HealthOmics
    (docs/PRODUCTION-MIGRATION.md §1, and required to be documented by requirements.md §15.1),
    is explicitly documented-not-built and is not free-tier, so adopting it also breaks the
    §14 free-tier envelope.
  Assessment vs prior pass: NOT resolved by ADRs 0013-0016. Its character is now clearer,
    though — this is not a hidden contradiction between documents. ADR-0011 declares the gap
    honestly in its own Consequences section, and requirements.md §15 mandates documenting the
    production path. It is an acknowledged, deliberate architectural limitation with no built
    remedy, not a doc conflict.
  → Decide and record explicitly before routing, choosing one of: (a) declare cloud execution
    of real genomics compute out of scope for this phase and state it in PROJECT.md so no
    roadmap item assumes it; (b) accept a bounded free-tier exception and write an ADR-0017
    adopting AWS HealthOmics as a real (not merely documented) execution path, which requires
    amending requirements.md §14.3/§14.5; or (c) keep local Nextflow as the sole real-compute
    path and scope cloud work to orchestration and metadata only.

[WARNING] W2 — Healer Lambda LLM runtime is unplaced against the free-tier Lambda envelope
  Found: docs/adr/0013-qc-warnings-adaptive-thresholds-self-healing.md (Accepted, LOCKED,
    precedence 0) specifies an "AI healer Lambda: Ollama-based diagnosis for ambiguous
    failures, with rule-based fallback" at lambdas/healer/handler.py, and lists Ollama
    availability as a dependency mitigated only by the rule-based fallback. It states no memory
    or timeout figure. docs/adr/0011-serverless-lambda-stepfunctions.md (Accepted, LOCKED) and
    requirements.md §2.2 / §14.2 cap every Lambda at 512 MB memory and 15 minutes.
  Impact: an Ollama model server does not fit in a 512 MB Lambda, so either the healer calls an
    Ollama endpoint hosted elsewhere (unstated, and there is no such component in the CDK stack
    list in design.md), or the free-tier Lambda cap is breached. Left unresolved, the roadmap
    could carry a healer task with no viable deployment target, and the "$0 idle" claim in
    ADR-0011 could quietly become false.
  Note on severity: this is recorded as a WARNING, not a BLOCKER, because neither locked
    document actually asserts a contradictory value — ADR-0013 is silent on the healer's
    memory and on where Ollama runs. Treating silence as a locked-vs-locked contradiction would
    be inference, not detection.
  → Have the author state where the healer's LLM runs (in-Lambda, an external Ollama endpoint,
    or a hosted provider as in ADR-0014's llm.py fallback chain), and either record the healer
    Lambda's memory/timeout or confirm the rule-based fallback is the cloud-deployed path with
    Ollama used only locally.

[WARNING] W3 — Measured validation scope is narrower than the locked project scope
  Found: docs/adr/0001-scope-giab-hg002-chr20.md (Accepted, LOCKED) fixes the region as
    "chromosome 20 only (and a ~1 Mb slice for the CI/test profile)" — the 1 Mb slice is
    scoped to CI, not to the analytical validation. docs/VALIDATION.md reports the only
    measured result (2026-07-15: HaplotypeCaller SNV precision 0.9934, recall 0.9894,
    F1 0.9914) as obtained on chr20:1,000,000-2,000,000, and §5 states plainly that this is
    "narrower than the 'chr20' scope in ADR-0001", that a full-chromosome run needs the full
    11 GB BAM, and that extending is "mechanical ... but not yet done". It also notes depth
    255.8x is unrepresentative of 30-40x clinical WGS because no downsampling was applied.
  Impact: the acceptance criterion SNV F1 >= 0.99 (ADR-0003, LOCKED) is currently evidenced
    only over 1/64th of the locked scope and at atypical depth. Any downstream plan that treats
    validation as complete would be overstating the evidence — directly against the project's
    stated non-overclaiming principle.
  → Either schedule the full-chr20 run (and a downsampled run) as a roadmap item that closes
    the evidence gap, or narrow ADR-0001's validated region with a new ADR. Precedence already
    resolves the authority question: ADR-0001 outranks VALIDATION.md, so the locked scope stays
    full chr20 and the evidence is what is incomplete.

[WARNING] W4 — Machine-verified immutability tests cover the demoted store, not the primary one
  Found: docs/adr/0016-cicd-strategy.md (Accepted, LOCKED, precedence 0) makes db-ci.yml a
    Tier 2 blocking check and justifies it as proving "schema integrity is machine-verified,
    not trust-based", with "immutability trigger tests validate the provenance/audit design in
    automation". Those trigger tests exercise the Postgres `forbid_mutation()` design from
    docs/adr/0005-insert-only-postgres.md. But docs/adr/0012-dynamodb-primary-store.md
    (Accepted, LOCKED) superseded ADR-0005 and demoted Postgres to a Metabase read-replica,
    and states explicitly that DynamoDB "has no equivalent" data-level control and that
    append-only there "rests on IAM policy, which a table administrator or the account root can
    bypass". requirements.md §7.2 requires the IAM deny policy to exist, but the guardrail
    tests it mandates in §7.4 assert only the absence of `*` resource ARNs and `iam:*` actions —
    no criterion requires a machine-verified assertion that the DynamoDB deny policy is present.
  Impact: the blocking, machine-verified integrity signal ADR-0016 advertises proves the
    integrity of the read-replica while the primary store's weaker, IAM-based control has no
    equivalent blocking check. The gap sits precisely on the project's headline
    ISO 15189-style tamper-evidence claim.
  → Add a CDK guardrail test asserting the `dynamodb:DeleteItem` / `dynamodb:UpdateItem` /
    `dynamodb:DeleteTable` deny statements are attached to all seven Lambda roles, and a check
    for the DynamoDB Streams audit sink named as compensating control #2 in ADR-0012 — then
    either amend ADR-0016's Tier 2 list or record the addition in a follow-up ADR.

Competing acceptance variants: 0. There are no PRD-classified documents and only one
requirements SPEC, so no requirement has two divergent acceptance definitions. Nothing was
merged or discarded.

### INFO (13)

[INFO] I1 — Auto-resolved: ADR-0015 supersedes the engine choice in ADR-0003 (vcfeval -> xcmp)
  Note: This was a stale-engine warning in the prior pass, raised because ADR-0003's Status
  line pointed at an ADR-0015 that was not yet in the ingest set. ADR-0015 is now present and
  the warning is RESOLVED. The supersession is explicit and reciprocal:
  docs/adr/0003-truth-set-validation.md reads "Status: Accepted, engine choice superseded by
  ADR-0015", and docs/adr/0015-happy-xcmp-engine-not-vcfeval.md reads "Supersedes: the engine
  choice in ADR-0003 (vcfeval); the rest of ADR-0003 — benchmarking as a first-class stage, the
  acceptance criterion, the alternatives rejected — stands unchanged." Because both locked
  documents declare the same partial supersession, this is a resolved sequence, not a
  locked-vs-locked contradiction. Final synthesized decision: the comparison engine is
  **xcmp**; the SNV F1 >= 0.99 acceptance criterion, the GIAB HG002 v4.2.1 truth set, the
  high-confidence BED restriction and ADR-0003's rejected alternatives all remain authoritative
  and unchanged. docs/VALIDATION.md already states xcmp and cites ADR-0015, so documentation is
  consistent — no drift to fix. Cause of record: the pinned image
  quay.io/biocontainers/hap.py:0.3.15--py27hcb73b3d_0 lacks rtg-tools, and the pkrusche/hap.py
  image that bundles it uses a manifest format modern Docker refuses.

[INFO] I2 — Auto-resolved: ADR-0012 supersedes ADR-0005 (insert-only Postgres -> DynamoDB primary)
  Note: Carried forward from the prior pass and re-confirmed. docs/adr/0005-insert-only-postgres.md
  carries "Status: Superseded by ADR-0012" and docs/adr/0012-dynamodb-primary-store.md carries
  "Supersedes: ADR-0005". DynamoDB single-table `cgp-metadata` is the primary metadata store;
  Postgres is retained as the Metabase read-replica so `v_run_summary` and the dashboard keep
  working. The "amend, never erase" semantic survives as `CORRECTION` records. ADR-0012 itself
  labels the weakened immutability guarantee "THE KEY HONEST TRADEOFF" and names three
  compensating detective controls (PITR, Streams -> append-only audit sink, writes restricted
  to the 7 scoped Lambda roles). Not a blocker.

[INFO] I3 — Auto-resolved: ADR-0011 partially supersedes ADR-0004 (compute only)
  Note: Carried forward from the prior pass and re-confirmed. ADR-0011 states "This supersedes
  only the compute decision of ADR-0004; the 'infrastructure as code via CDK, reviewed in CI,
  tagged with data classification' and the S3 data-lake decisions of ADR-0004 are retained."
  Synthesis therefore keeps ADR-0004's CDK/IaC choice, S3 data lake, scoped IAM and Jest
  guardrail-test invariants (bucket versioning, public-access block, TLS-only, deny-delete on
  raw/results) as authoritative, and marks only Batch-on-Fargate as superseded.

[INFO] I4 — Reference cycles are reciprocal ADR backlinks; recorded, not blocking
  Note: Cycle detection ran over the cross_refs graph with three-colour DFS. Six cycles found,
  all 2- or 3-node reciprocal links: ADR-0004 <-> ADR-0011 and ADR-0005 <-> ADR-0012 (both
  supersedes / superseded-by pairs); ADR-0003 <-> ADR-0015 (partial-supersession pair via
  ADR-0003's Status line); ADR-0003 <-> docs/VALIDATION.md <-> ADR-0015; ADR-0010 <->
  docs/GA4GH-ALIGNMENT.md; docs/BEGINNERS-GUIDE.md <-> docs/GLOSSARY.md. Reciprocal
  supersedes/superseded-by backlinks between ADR pairs are this project's required append-only
  convention — CLAUDE.md mandates "supersede it and update its status", which necessarily
  creates a link in both directions. A cycle arising solely from that convention carries no
  information hazard. The remaining cycles are ordinary "see also" links between a document and
  its companion. Synthesis treats every document as an independent node and never expands
  cross_refs transitively, so no synthesis loop is possible from any of these. Recorded as INFO
  per the established resolution; no document was excluded from synthesis. Max traversal depth
  reached: 3 (cap 50).

[INFO] I5 — Auto-resolved: ADR > DOC/ADR-consequence on residual AWS Batch references
  Note: docs/adr/0002-nextflow-dsl2-pipeline.md (Consequences), docs/adr/0009-docker-pinned-by-digest.md
  (Alternatives), docs/SOP-run-pipeline.md, docs/usage.md and docs/MILESTONES.md (milestone M4,
  "the same pipeline runs on AWS Batch unmodified") all still describe AWS Batch as the cloud
  execution path. ADR-0011 (Accepted, LOCKED) removed Batch/Fargate. ADR-0011 wins. The core
  decisions of ADR-0002 (Nextflow DSL2 / nf-core) and ADR-0009 (per-step containers pinned by
  digest) are untouched — only their incidental Batch mentions are stale. The DOC-level
  mentions are lowest precedence and are recorded in intel/context.md as documentation drift.

[INFO] I6 — Auto-resolved: ADR-0009 > SPEC on container tag pinning
  Note: .kiro/specs/clinical-genomics-platform/requirements.md §12.1 permits pinning "by exact
  version tag for images from registries that do not publish digests".
  docs/adr/0009-docker-pinned-by-digest.md (Accepted, LOCKED) requires immutable sha256 digest
  pinning in production and explicitly rejects tag pinning ("tags can be re-pushed; digests are
  the only truly immutable reference"). ADR wins. Synthesized constraint: digest pinning is
  mandatory for every pipeline step, and §12.1's tag exemption is narrowed to registries that
  genuinely cannot supply a digest. §12.4 (Metabase pinned to an exact release tag) is
  unaffected — Metabase is not a pipeline step and falls outside ADR-0009's scope.

[INFO] I7 — Auto-resolved: ADR-0016 > SPEC on CI workflow permissions
  Note: requirements.md §13.7 requires "only read-level repository permissions (contents: read)
  for all workflow jobs". docs/adr/0016-cicd-strategy.md (Accepted, LOCKED, precedence 0)
  postdates it and requires elevated scopes on specific workflows — `issues: write` for
  maintenance.yml auto-issue creation, security-events write for SARIF upload, packages write
  for the GHCR push in docker.yml, pull-requests write for coverage PR comments, and contents
  write for release.yml. ADR wins by both default ordering and its precedence-0 override.
  Synthesized constraint: least privilege per workflow, which is more than contents:read for
  those five. Flagged here because it is a genuine narrowing of a security invariant, resolved
  by precedence rather than by judgement.

[INFO] I8 — Auto-resolved: ADR-0013 extends the SPEC DynamoDB record_type enum
  Note: requirements.md §5.2 restricts `record_type` to {RUN, QC_METRICS, PROVENANCE, AUDIT,
  CORRECTION}. ADR-0013 (LOCKED, precedence 0) adds a `QC_WARNING` record type carrying full
  evaluation detail (lambdas/shared/models.py). ADR wins; the enum is extended, not replaced.
  design.md §Correctness Property 5 (DynamoDB record type validation) will need the sixth value.

[INFO] I9 — Auto-resolved: ADR-0013 extends the SPEC Step Functions state list
  Note: requirements.md §2.1 fixes a seven-state sequence (trigger ingestion, QC checks,
  variant calling, validate, export, ingest metadata, generate report). ADR-0013 (LOCKED,
  precedence 0) adds Choice states for deterministic failure routing, a healer Lambda invocation,
  a CheckHealingLimit guard and a notify-then-wait state, plus a `QC_EVALUATE` Nextflow process
  after `HAPPY_BENCHMARK`. ADR wins; the sequence is extended, not replaced. The
  maxConcurrency:1 and 4,000-transitions/month constraints from ADR-0011 and requirements.md
  §14.7 still bound the extended machine.

[INFO] I10 — Auto-resolved: the Kiro spec predates ADRs 0013-0016
  Note: .kiro/specs/clinical-genomics-platform/{requirements,design,tasks}.md describe the
  serverless rearchitecture only. tasks.md marks all 17 tasks complete and contains no task for
  the QC warning layer, the agentic interpreter, the xcmp engine switch or the tiered CI/CD.
  design.md's five-stack list and 13 correctness properties likewise predate them. ADRs outrank
  SPECs, so the four newer ADRs are additive and authoritative over the spec where they overlap
  (see I8, I9, I7). No spec content was discarded — the unaffected majority stands and is
  recorded in intel/constraints.md.

[INFO] I11 — Auto-resolved: docs/adr/README.md index is stale (lists 12 of 16 ADRs)
  Note: The ADR index enumerates ADR-0001 through ADR-0012 only; ADR-0013, 0014, 0015 and 0016
  are absent. This is incompleteness in a DOC, not a contradiction — the four ADRs are present
  on disk, Accepted, and classified. ADR precedence resolves authority; the index is a
  navigation aid. docs/MILESTONES.md already reports "Architecture Decision Records (16 ADRs)",
  so the repo's own status table is ahead of its index. Recorded as documentation drift in
  intel/context.md. Note that docs/ROADMAP.md item P0-1 already flagged index maintenance as
  required work.

[INFO] I12 — Auto-resolved: ADR-0014 number collides with a number reserved in ROADMAP.md
  Note: docs/ROADMAP.md cross-references `docs/adr/0014-spatial-genomics-direction.md` as a
  planned ADR. The number 0014 was taken by docs/adr/0014-agentic-variant-interpretation.md
  (Accepted, LOCKED). ADR wins over the DOC by precedence: ADR-0014 is agentic variant
  interpretation, and the ROADMAP reference is a dangling link to a file that does not and will
  not exist under that number. A future spatial-genomics ADR must take the next free number.

[INFO] I13 — Auto-resolved: docs/END-TO-END.md placeholder-validation claim is date-scoped
  Note: docs/END-TO-END.md records the 2026-07-14 run and states "Accuracy numbers are not real
  yet ... docs/VALIDATION.md remains placeholder, correctly", because that run was stub-mode.
  docs/VALIDATION.md now reports a real measured run from 2026-07-15. Both are DOC precedence,
  so this was not resolved by ranking or by timestamp: END-TO-END.md is explicitly framed as a
  dated record of one specific execution ("A real execution ... run on 2026-07-14"), so it does
  not assert a present-tense claim that competes with VALIDATION.md. No contradiction. What
  END-TO-END.md does independently evidence remains valid and is preserved in intel/context.md —
  notably that the Postgres insert-only triggers were observed rejecting `UPDATE runs` and
  `DELETE FROM audit_log` in a real database.
