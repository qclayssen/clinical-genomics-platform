# Roadmap: Clinical Genomics Insight Platform

## Overview

The platform is already built — milestones M0–M8 delivered the pipeline, infrastructure, data
layer, dashboard, AI reporting, agentic interpreter, CI and demo. This milestone does not rebuild
any of it. It closes the distance between what the repo **claims** and what it has **proven**.

Five phases, ordered by what unblocks the most. Phase 1 settles the one architectural question
that has no answer today — where real genomics compute runs — because every downstream document
and every future cloud task depends on it. Phase 2 makes the machine-verified integrity claim
actually true: the blocking CI posture and a guardrail that covers the *primary* store rather
than the demoted replica. Phase 3 produces the headline evidence: a full-chr20, representative-
depth `hap.py` run, because everything the project claims rests on SNV F1 ≥ 0.99 over the locked
scope. Phase 4 brings the documentation back in line, once Phases 1 and 3 have settled what the
truth is. Phase 5 guarantees the reviewer's three-minute clickthrough works and shows the new
evidence beside its limits.

**Granularity:** standard · **Phase ID convention:** sequential

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [ ] **Phase 1: Execution Substrate Decision** - Record one authoritative answer to where real genomics compute runs, and make every document agree with it
- [ ] **Phase 2: Machine-Verified Integrity** - Make the blocking CI posture and the tamper-evidence guarantee true for the primary store, not just the replica
- [ ] **Phase 3: Full-Scope Validation Evidence** - Measure SNV F1 over the full locked chr20 scope at representative depth and record it honestly
- [ ] **Phase 4: Documentation Accuracy** - Bring CLAUDE.md, the ADR index and cross-references back in line with 16 ADRs and the current architecture
- [ ] **Phase 5: Reviewer Clickthrough** - Guarantee the three-minute demo path works and shows the measured evidence beside its limits

## Phase Details

### Phase 1: Execution Substrate Decision
**Goal**: Anyone reading the repo gets exactly one answer to "where does real genomics compute
run?", and no document contradicts it.
**Depends on**: Nothing (first phase)
**Requirements**: EXEC-01, EXEC-02, EXEC-03
**Success Criteria** (what must be TRUE):
  1. A reader can open one Accepted ADR and learn the authoritative cloud-execution position for
     real genomics compute, with the rejected options and their cost stated.
  2. Searching the repo for AWS Batch as a cloud execution path returns nothing that contradicts
     that ADR — `docs/SOP-run-pipeline.md`, `docs/usage.md`, `docs/MILESTONES.md` M4 and the
     ADR-0002/ADR-0009 asides all agree.
  3. A reader can determine from the repo where the healer's LLM runs and whether it fits the
     512 MB / 15 min envelope, without inferring it from source code.
  4. A test fails if the deployed healer path is changed to require an in-Lambda Ollama server.
**Plans**: TBD

**Why first:** this is the only genuinely open architectural question in the project. Every
documentation fix in Phase 4 and every future cloud task would otherwise be planned against a
capability that does not exist. It is a decision phase — the outcome is an ADR plus alignment,
not a build.

**Non-negotiable:** the decision is recorded as a new next-numbered ADR. ADR-0011 is not edited.
If the choice is option (b) HealthOmics, `.kiro/specs/.../requirements.md` §14.3/§14.5 must be
amended in the same change so the CDK guardrail tests and the free-tier claim stay coherent.

### Phase 2: Machine-Verified Integrity
**Goal**: The project's headline claim — that integrity is machine-verified, not trust-based —
holds for the store that actually holds the data, and the checks that prove it can fail a merge.
**Depends on**: Phase 1
**Requirements**: INTEG-01, INTEG-02, INTEG-03, CI-01, CI-02, CI-03
**Success Criteria** (what must be TRUE):
  1. Deliberately removing a `dynamodb:DeleteItem` deny statement from any one Lambda role turns
     a CDK guardrail test red.
  2. Deliberately breaking an immutability trigger in `db/schema.sql` turns the `db-ci.yml`
     status check red — the job exits non-zero rather than printing a warning and passing.
  3. A pull request against this repo shows 6 or more status checks, each reporting its real
     result.
  4. A reader can find, in one place, an accurate statement of what tamper-evidence the primary
     DynamoDB store has (IAM-based, bypassable by a table admin or account root) versus what the
     Postgres replica has (trigger-based, data-level) — with the Streams audit sink either built
     and asserted, or named as an accepted limitation.
**Plans**: TBD

**Context:** `infra/test/stacks.test.ts:163` already asserts the deny actions exist somewhere in
the synthesized IAM template. That is weaker than the invariant it appears to prove — it does not
establish per-role attachment. Strengthening it is the substance of INTEG-01.

**Context:** the uncommitted working-tree change wrapping CI steps in `|| echo "non-blocking"` is
the direct cause of CI-01/CI-02. CI-03 forces a choice: revert it, or supersede ADR-0016 with a
new ADR that states why non-blocking checks are acceptable. Silently leaving both in place is the
one outcome this phase must not produce.

### Phase 3: Full-Scope Validation Evidence
**Goal**: The primary success metric is evidenced over the locked scope, at a depth a reviewer
would recognise as clinically representative.
**Depends on**: Phase 1 (the execution path for the run must be settled), Phase 2 (re-validation
is gated by blocking checks)
**Requirements**: VAL-01, VAL-02, VAL-03
**Success Criteria** (what must be TRUE):
  1. `docs/VALIDATION.md` reports measured SNV precision, recall and F1 for a full-chr20 run,
     with the run's provenance stamp — git commit, pipeline version, caller version, reference
     version, truth-set version, input checksums.
  2. `docs/VALIDATION.md` reports a second measured run at ~30–40× downsampled depth, so no
     reported metric depends on the unrepresentative 255.8× source depth.
  3. A reader comparing `docs/VALIDATION.md` against ADR-0001 finds the validated region matches
     the locked scope — or finds a new ADR that narrows the scope and says why.
  4. The stated limitations survive the update: single sample, high-confidence BED exclusions,
     xcmp's conservatism on complex representations, INDEL reported but not gated.
**Plans**: TBD

**Environment:** this phase needs Nextflow + Docker + the staged 11 GB GIAB BAM locally. It is
the only phase in this milestone that cannot run in a dependency-free environment. If the run
cannot be completed, the honest outcome is criterion 3's alternative — a new ADR narrowing the
validated region — not a placeholder number. Never commit an unmeasured figure to
`docs/VALIDATION.md`.

**Re-validation rule (ADR-0003):** any change to reference, caller or filtering re-triggers this
benchmark before tagging. Acceptance criterion SNV F1 ≥ 0.99, `hap.py` xcmp engine (ADR-0015),
GIAB HG002 v4.2.1 high-confidence BED.

### Phase 4: Documentation Accuracy
**Goal**: A reader onboarding from the repo's own documents is not misled about the architecture,
the decision record, or what has been superseded.
**Depends on**: Phase 1 (substrate decision), Phase 3 (measured numbers)
**Requirements**: DOC-01, DOC-02, DOC-03
**Success Criteria** (what must be TRUE):
  1. `CLAUDE.md` states the correct ADR count and no longer presents insert-only Postgres as the
     primary store's non-negotiable — the DynamoDB primary and its weaker IAM-based control are
     described accurately, with "amend, never erase" preserved as the surviving semantic.
  2. `docs/adr/README.md` lists every ADR file present on disk with its correct status, including
     every supersession.
  3. Following any ADR cross-reference in the docs lands on a file that exists — the dangling
     `0014-spatial-genomics-direction.md` reference is resolved.
**Plans**: TBD

**Why after Phases 1 and 3:** writing these documents before the substrate decision and the
measured numbers exist would mean writing them twice, and would risk recording a claim that
Phase 1 or Phase 3 then contradicts.

**Convention:** ADRs are append-only. Correcting the index and cross-references is allowed;
rewriting the body of an Accepted ADR is not.

### Phase 5: Reviewer Clickthrough
**Goal**: A hiring manager with three minutes and no setup can see the platform work and
understand exactly what they are and are not looking at.
**Depends on**: Phase 3 (measured numbers to surface), Phase 4 (documents to link)
**Requirements**: DEMO-01, DEMO-02, DEMO-03
**Success Criteria** (what must be TRUE):
  1. Following the documented entry point, a reviewer reaches a running demo and completes
     home → explorer → variant interpretation → assistant within three minutes, with no database,
     no cloud account and no LLM.
  2. The demo displays the Phase 3 measured validation numbers alongside the scope statement —
     full chr20, germline SNVs, GIAB HG002, portfolio project, not an accredited clinical test.
  3. On every page, a reviewer can tell at a glance which output is real measured data, which is
     committed seed data, and which is a deterministic stand-in for an unavailable service.
  4. No screen presents AI-drafted text without the `AI-DRAFTED — REQUIRES CLINICIAN REVIEW`
     banner and its provenance line.
**Plans**: TBD
**UI hint**: yes

**Scope guard:** this is a clarity and honesty pass over the existing Streamlit app
(`demo/app.py`, `demo/pages/{home,explorer,interpret,chat}.py`), not a redesign. Criterion 4
restates ADR-0008 and ADR-0014 — those guardrails are enforced in code and must not be weakened
to improve the demo's appearance.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Execution Substrate Decision | 0/TBD | Not started | - |
| 2. Machine-Verified Integrity | 0/TBD | Not started | - |
| 3. Full-Scope Validation Evidence | 0/TBD | Not started | - |
| 4. Documentation Accuracy | 0/TBD | Not started | - |
| 5. Reviewer Clickthrough | 0/TBD | Not started | - |

## Coverage

All 18 v1 requirements mapped to exactly one phase. No orphans, no duplicates.
See `.planning/REQUIREMENTS.md` → Traceability.

The 19 delivered baseline requirements (M0–M8) are intentionally **not** mapped to phases — they
are already built. Their partial gaps are carried into v1 scope as EXEC, INTEG and CI
requirements rather than by re-planning the original work.
