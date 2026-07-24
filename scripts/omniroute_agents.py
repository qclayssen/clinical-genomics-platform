#!/usr/bin/env python3
"""Multi-profile agent orchestration for Clinical Genomics Platform phases.

Routes each phase to a specialized Claude Code profile (genomics-reasoning,
genomics-nextflow, genomics-infra, etc.) by spawning separate `claude` CLI
sessions with the --profile flag.

Unlike omniroute_review.py (which reviews code changes), this orchestrates
implementation work across the 5 roadmap phases with appropriate model combos.

Prerequisites:
    - Claude Code CLI installed and authenticated
    - Profiles configured: genomics-reasoning, genomics-nextflow, genomics-infra, genomics-free
    - Working directory: repo root

Usage:
    python scripts/omniroute_agents.py --phase 1
    python scripts/omniroute_agents.py --phase all
    python scripts/omniroute_agents.py --phase 1,2,3
"""
import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parent.parent

PhaseID = Literal[1, 2, 3, 4, 5]

# Map each phase to the most appropriate profile based on domain
PHASE_PROFILES = {
    1: {
        "name": "Phase 1: Execution Substrate Decision",
        "profile": "genomics-reasoning",  # Architectural decision-making
        "description": "Record authoritative answer to where real genomics compute runs",
        "depends_on": [],
        "prompt": """You're working on the Clinical Genomics Insight Platform.

**Your task (Phase 1):** Record one authoritative answer to "where does real genomics compute run?" and make every document agree with it.

**Context:**
- ADR-0011 states Lambda cannot run BWA-MEM2/DeepVariant/hap.py (memory/time constraints)
- REQ-cost-guardrails forbids AWS Batch/Fargate/NAT/RDS (CDK guardrail tests assert zero)
- The healer Lambda calls `http://localhost:11434` (Ollama), which doesn't exist in 512MB Lambda
- Docs currently contradict: some say Batch, some say local Nextflow, some say HealthOmics

**Three options:**
(a) Declare cloud execution out-of-scope; document local Nextflow as sole real-compute path
(b) Supersede with new ADR adopting AWS HealthOmics; amend .kiro/specs requirements §14.3/§14.5
(c) Hybrid: cloud for orchestration/metadata only, local for real compute

**Deliverables:**
1. New next-numbered ADR (ADR-0017) with the chosen substrate, rejected options, cost implications
2. Align docs/SOP-run-pipeline.md, docs/usage.md, docs/MILESTONES.md M4 with the ADR
3. Document or fix healer Ollama placement (if option a/c, state rule-based fallback is the cloud path)
4. If option (b), amend .kiro/specs requirements and update CDK guardrail tests

**Constraints:**
- ADRs are append-only; never edit an existing one
- If choosing HealthOmics (option b), the free-tier claim in §14.3 must change
- A test must fail if deployment contradicts the chosen substrate

Complete Phase 1 per .planning/ROADMAP.md success criteria. Output a final status report.""",
    },
    2: {
        "name": "Phase 2: Machine-Verified Integrity",
        "profile": "genomics-infra",  # Infrastructure/CI work
        "description": "Make blocking CI posture and tamper-evidence guarantee true",
        "depends_on": [1],
        "prompt": """You're working on the Clinical Genomics Insight Platform.

**Your task (Phase 2):** Make the blocking CI posture and tamper-evidence guarantee true for the primary DynamoDB store, not just the Postgres replica.

**Context:**
- Uncommitted working-tree changes wrap CI steps in `|| echo "non-blocking"` (contradicts ADR-0016)
- infra/test/stacks.test.ts:163 asserts deny actions exist *somewhere*, not per-role attachment
- No DynamoDB Streams audit sink exists in infra/lib/metadata-stack.ts (ADR-0012 names it as compensating control)
- db-ci.yml should exit non-zero on trigger breaks, currently continues

**Deliverables:**
1. Remove `|| echo` wrappers from .github/workflows/{db-ci,lint,pipeline-ci,infra-ci,security}.yml
2. Strengthen CDK test to assert dynamodb:DeleteItem/UpdateItem deny on *every* Lambda role that writes to cgp-metadata
3. Fix db-ci.yml to exit non-zero when immutability trigger test fails
4. Either build the Streams→audit-sink or document IAM-only control as accepted limitation in docs/

**Constraints:**
- Must restore ADR-0016's "machine-verified and blocking" requirement
- PRs must show 6+ real status checks
- If not building Streams sink, state honestly that IAM is bypassable by table admin/account root

Complete Phase 2 per .planning/ROADMAP.md success criteria. Output a final status report.""",
    },
    3: {
        "name": "Phase 3: Full-Scope Validation Evidence",
        "profile": "genomics-nextflow",  # Pipeline/Nextflow execution
        "description": "Measure SNV F1 over full chr20 at representative depth",
        "depends_on": [1, 2],
        "prompt": """You're working on the Clinical Genomics Insight Platform.

**Your task (Phase 3):** Measure SNV F1 over full chr20 at representative depth and record it honestly.

**Context:**
- Current evidence: chr20:1,000,000-2,000,000 (1/64th scope) at 255.8× (unrepresentative)
- Acceptance: SNV F1 ≥ 0.99 via hap.py xcmp engine (ADR-0003, ADR-0015)
- ADR-0001 locks scope to full chr20, germline SNVs, GIAB HG002 v4.2.1 high-confidence BED
- Requires Nextflow + Docker + staged 11GB GIAB HG002 BAM locally

**Deliverables:**
1. Run hap.py on full chr20 (not just the 1Mb window)
2. Run second validation at ~30-40× downsampled depth (representative of clinical WGS)
3. Update docs/VALIDATION.md with measured precision/recall/F1 + provenance stamp (git commit, pipeline version, caller version, reference version, truth-set version, input checksums)
4. If full-chr20 run cannot complete, create ADR-0018 narrowing the validated region and state why

**Constraints:**
- Never commit unmeasured/placeholder numbers to docs/VALIDATION.md
- Preserve limitation statements: single sample, high-confidence BED exclusions, xcmp conservatism, INDEL reported but not gated
- Re-validation rule: any reference/caller/filtering change re-triggers this before tagging

Complete Phase 3 per .planning/ROADMAP.md success criteria. Output a final status report.""",
    },
    4: {
        "name": "Phase 4: Documentation Accuracy",
        "profile": "genomics-reasoning",  # Documentation alignment/reasoning
        "description": "Bring CLAUDE.md, ADR index, and cross-references in line",
        "depends_on": [1, 3],
        "prompt": """You're working on the Clinical Genomics Insight Platform.

**Your task (Phase 4):** Bring CLAUDE.md, ADR index, and cross-references in line with 16 ADRs and current architecture.

**Context:**
- CLAUDE.md claims 9 ADRs (16 exist), presents insert-only Postgres as non-negotiable (ADR-0012 superseded it)
- docs/adr/README.md indexes 12 of 16 ADRs
- Dangling cross-references exist (e.g., docs/ROADMAP.md reserves ADR-0014, which is taken)
- Phase 1 settled the execution substrate, Phase 3 produced measured numbers

**Deliverables:**
1. Update CLAUDE.md: correct ADR count to 16, describe DynamoDB as primary with IAM-based control (weaker than trigger-level), preserve "amend never erase" semantic
2. Update docs/adr/README.md: list all 16 ADRs with correct status, including supersessions (ADR-0004→ADR-0011, ADR-0005→ADR-0012)
3. Fix all dangling ADR cross-references in docs/ (grep for ADR-0014, ADR-0017, ADR-0018 references)
4. Ensure docs/SOP-run-pipeline.md, docs/usage.md, docs/MILESTONES.md M4 agree with Phase 1's substrate ADR

**Constraints:**
- ADRs themselves are append-only; never edit an Accepted ADR body
- Only fix the index and cross-references, not the ADR decisions

Complete Phase 4 per .planning/ROADMAP.md success criteria. Output a final status report.""",
    },
    5: {
        "name": "Phase 5: Reviewer Clickthrough",
        "profile": "genomics-free",  # Demo verification (simple, use free tier)
        "description": "Guarantee three-minute reviewer clickthrough works",
        "depends_on": [3, 4],
        "prompt": """You're working on the Clinical Genomics Insight Platform.

**Your task (Phase 5):** Guarantee the three-minute reviewer clickthrough works and overclaims nothing.

**Context:**
- Demo is Streamlit (demo/app.py + demo/pages/{home,explorer,interpret,chat}.py)
- Phase 3 produced measured validation numbers to surface
- Must distinguish real measured data / committed seed data / deterministic stand-ins

**Deliverables:**
1. Test the documented entry point and verify home → explorer → variant interpretation → assistant completes in <3 min (no DB, no cloud, no LLM required)
2. Display Phase 3 measured validation numbers + scope statement on appropriate page (full chr20, germline SNVs, GIAB HG002, portfolio project, not accredited)
3. On every page, make it clear which output is real/seed/deterministic
4. Verify AI-DRAFTED — REQUIRES CLINICIAN REVIEW banner + provenance line appears on all LLM output

**Constraints:**
- This is a clarity pass, not a redesign of demo/
- ADR-0008 and ADR-0014 guardrails must not be weakened for appearance
- Deterministic fallback paths are acceptable; label them clearly

Complete Phase 5 per .planning/ROADMAP.md success criteria. Output a final status report.""",
    },
}


async def run_phase(phase: PhaseID, dry_run: bool = False) -> dict:
    """Run a single phase using its assigned profile."""
    config = PHASE_PROFILES[phase]
    print(f"\n{'='*80}")
    print(f"Phase {phase}: {config['name']}")
    print(f"Profile: {config['profile']}")
    print(f"Description: {config['description']}")
    print(f"{'='*80}\n")

    if dry_run:
        print(f"[DRY RUN] Would execute with profile: {config['profile']}")
        return {"phase": phase, "status": "dry_run", "profile": config["profile"]}

    # Write prompt to a temp file so we can pass it via stdin or --file
    prompt_file = REPO_ROOT / f".planning/.phase{phase}_prompt.txt"
    prompt_file.write_text(config["prompt"])

    # Spawn claude CLI with the appropriate profile
    cmd = [
        "claude",
        "--profile", config["profile"],
        "--",
        config["prompt"],
    ]

    print(f"Executing: {' '.join(cmd[:4])}... (prompt hidden)")

    try:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 min timeout
        )

        output_file = REPO_ROOT / f".planning/.phase{phase}_output.txt"
        output_file.write_text(result.stdout)

        if result.returncode != 0:
            print(f"❌ Phase {phase} failed with exit code {result.returncode}")
            print(f"stderr: {result.stderr}")
            return {
                "phase": phase,
                "status": "failed",
                "exit_code": result.returncode,
                "output_file": str(output_file),
            }

        print(f"✅ Phase {phase} completed successfully")
        print(f"Output saved to: {output_file}")

        return {
            "phase": phase,
            "status": "completed",
            "output_file": str(output_file),
        }

    except subprocess.TimeoutExpired:
        print(f"⏱️  Phase {phase} timed out after 30 minutes")
        return {"phase": phase, "status": "timeout"}

    except Exception as e:
        print(f"❌ Phase {phase} errored: {e}")
        return {"phase": phase, "status": "error", "error": str(e)}

    finally:
        prompt_file.unlink(missing_ok=True)


async def run_phases(phases: list[PhaseID], dry_run: bool = False, parallel: bool = False) -> list[dict]:
    """Run multiple phases respecting dependencies."""
    completed = set()
    results = []

    # Sort phases by dependency order
    sorted_phases = []
    remaining = set(phases)

    while remaining:
        ready = [
            p for p in remaining
            if all(dep in completed or dep not in phases for dep in PHASE_PROFILES[p]["depends_on"])
        ]

        if not ready:
            print("❌ Circular dependency detected or missing prerequisites!")
            break

        sorted_phases.extend(ready)
        remaining -= set(ready)

    print(f"\nExecution order: {sorted_phases}")
    print(f"Parallel: {parallel}\n")

    if parallel:
        # Run phases in parallel batches respecting dependencies
        batch = []
        for phase in sorted_phases:
            deps = PHASE_PROFILES[phase]["depends_on"]
            if all(d in completed for d in deps):
                batch.append(phase)
            else:
                # Execute current batch
                if batch:
                    batch_results = await asyncio.gather(*[run_phase(p, dry_run) for p in batch])
                    results.extend(batch_results)
                    completed.update(batch)
                    batch = []
                # Start new batch
                batch.append(phase)

        # Execute final batch
        if batch:
            batch_results = await asyncio.gather(*[run_phase(p, dry_run) for p in batch])
            results.extend(batch_results)
    else:
        # Sequential execution
        for phase in sorted_phases:
            result = await run_phase(phase, dry_run)
            results.append(result)
            if result["status"] == "completed":
                completed.add(phase)
            else:
                print(f"⚠️  Phase {phase} did not complete successfully, continuing anyway...")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--phase",
        default="all",
        help="Phase(s) to run: 1-5, 'all', or comma-separated list (e.g., '1,2,3')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be executed without running",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run independent phases in parallel (experimental)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all phases with their assigned profiles",
    )
    args = parser.parse_args()

    if args.list:
        print("\nAvailable Phases:\n")
        for phase_id, config in sorted(PHASE_PROFILES.items()):
            deps = ", ".join(map(str, config["depends_on"])) if config["depends_on"] else "none"
            print(f"Phase {phase_id}: {config['name']}")
            print(f"  Profile: {config['profile']}")
            print(f"  Depends on: {deps}")
            print(f"  Description: {config['description']}\n")
        return 0

    # Parse phase selection
    if args.phase == "all":
        phases = list(PHASE_PROFILES.keys())
    else:
        try:
            phases = [int(p.strip()) for p in args.phase.split(",")]
            if not all(p in PHASE_PROFILES for p in phases):
                print(f"Invalid phase(s). Must be 1-5.", file=sys.stderr)
                return 1
        except ValueError:
            print(f"Invalid phase format: {args.phase}", file=sys.stderr)
            return 1

    print(f"Selected phases: {phases}")
    print(f"Dry run: {args.dry_run}")
    print(f"Parallel: {args.parallel}")

    results = asyncio.run(run_phases(phases, args.dry_run, args.parallel))

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")

    for result in results:
        status_icon = {
            "completed": "✅",
            "failed": "❌",
            "timeout": "⏱️ ",
            "error": "❌",
            "dry_run": "🔍",
        }.get(result["status"], "❓")

        print(f"{status_icon} Phase {result['phase']}: {result['status']}")
        if "output_file" in result:
            print(f"   Output: {result['output_file']}")

    failed = [r for r in results if r["status"] not in ("completed", "dry_run")]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
