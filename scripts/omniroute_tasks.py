#!/usr/bin/env python3
"""Multi-model task execution via OmniRoute gateway with explicit model routing.

Unlike omniroute_review.py (which reviews code changes), this executes tasks by
calling the OmniRoute OpenAI-compatible endpoint with domain-appropriate models.

Each task gets routed to a specialized model combo:
- ADR decisions, architectural reasoning → genomics-reasoning
- Nextflow, pipeline work → genomics-nextflow
- CI/CD, infrastructure → genomics-infra
- Demo, simple tasks → genomics-free

Prerequisites:
    omniroute running on http://localhost:20128
    export OMNIROUTE_API_KEY=... (Dashboard > Settings > API Keys)

Usage:
    python scripts/omniroute_tasks.py --task compliance-audit --pr 46,47,48,49
    python scripts/omniroute_tasks.py --task fix-trivy --pr 48
    python scripts/omniroute_tasks.py --list-models
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_URL = os.getenv("OMNIROUTE_BASE_URL", "http://localhost:20128")
API_KEY = os.getenv("OMNIROUTE_API_KEY")

# Map task types to OmniRoute model names
TASK_MODELS = {
    "adr-decision": {
        "model": "genomics-reasoning",
        "description": "Architectural decisions, ADR writing, system design",
    },
    "pipeline-work": {
        "model": "genomics-nextflow",
        "description": "Nextflow DSL2, bioinformatics pipeline development",
    },
    "infra-work": {
        "model": "genomics-infra",
        "description": "AWS CDK, CI/CD, infrastructure, security",
    },
    "demo-work": {
        "model": "genomics-free",
        "description": "Demo app, simple documentation updates",
    },
    "compliance-audit": {
        "model": "genomics-reasoning",
        "description": "ISO 15189 / NATA compliance review",
    },
    "fix-trivy": {
        "model": "genomics-infra",
        "description": "Fix Trivy security scan failures",
    },
}


async def call_omniroute(model: str, system_prompt: str, user_prompt: str) -> dict:
    """Call OmniRoute gateway with explicit model routing."""
    headers = {}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            response = await client.post(
                f"{BASE_URL}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.3,
                    "stream": False,
                },
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"]
            cost = response.headers.get("x-omniroute-response-cost", "0.0")

            return {
                "model": model,
                "content": content,
                "cost": float(cost),
                "usage": data.get("usage", {}),
            }

        except httpx.ConnectError:
            print(f"❌ Could not reach OmniRoute at {BASE_URL}", file=sys.stderr)
            print("   Is `omniroute` running? Start with: omniroute", file=sys.stderr)
            sys.exit(1)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                print("❌ Unauthorized - set OMNIROUTE_API_KEY", file=sys.stderr)
            else:
                print(f"❌ OmniRoute error: {e}", file=sys.stderr)
            sys.exit(1)


async def task_compliance_audit(prs: list[int]) -> dict:
    """Audit PRs for clinical genomics compliance using genomics-reasoning model."""
    model = TASK_MODELS["compliance-audit"]["model"]

    system_prompt = """You are a compliance auditor for a clinical genomics platform.

Review pull requests against ISO 15189 / NATA accreditation requirements:
- Provenance completeness
- Insert-only invariants (no update/delete paths)
- Validation freshness (re-validation triggers)
- Audit-trail coverage
- Change control (ADR append-only)
- Honest scoping (no overclaims)"""

    user_prompt = f"""Audit PRs {', '.join(f'#{pr}' for pr in prs)} for compliance.

For each PR:
1. Get the diff: `gh pr diff {prs[0]}`
2. Check against the 6 compliance criteria above
3. Output findings by severity (critical/medium/minor)
4. Give compliance status: PASS / NEEDS_REVISION / BLOCKED

Focus on traceability patterns, not implementation bugs."""

    print(f"\n🔍 Running compliance audit via {model}...")
    result = await call_omniroute(model, system_prompt, user_prompt)

    print(f"✅ Audit complete (cost: ${result['cost']:.4f})")
    return result


async def task_fix_trivy(pr: int) -> dict:
    """Fix Trivy CI failures using genomics-infra model."""
    model = TASK_MODELS["fix-trivy"]["model"]

    system_prompt = """You are a security engineer fixing Trivy vulnerability scan failures in CI/CD.

Your goal: make Trivy pass while keeping exit-code: '1' (blocking behavior per ADR-0016).

Common fixes:
- Update Python dependencies (requirements.txt)
- Update npm packages (package.json)
- Add .trivyignore with security justification if false positives
- Pin secure versions in Dockerfiles

Document any suppressions with rationale."""

    user_prompt = f"""Fix Trivy filesystem scan failures on PR #{pr}.

Steps:
1. Get failure logs: `gh run view <run-id> --log-failed | grep -A 50 CRITICAL`
2. Identify vulnerable dependencies
3. Update to patched versions OR suppress with justification
4. Keep exit-code: '1' (don't disable blocking)

Output: specific fixes needed with commands to apply them."""

    print(f"\n🔧 Fixing Trivy failures via {model}...")
    result = await call_omniroute(model, system_prompt, user_prompt)

    print(f"✅ Fix plan ready (cost: ${result['cost']:.4f})")
    return result


def list_models():
    """List available task-to-model mappings."""
    print("\n📋 Available Tasks and Model Routing:\n")
    for task_type, config in TASK_MODELS.items():
        print(f"  {task_type}")
        print(f"    Model: {config['model']}")
        print(f"    Description: {config['description']}\n")


async def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--task", choices=list(TASK_MODELS.keys()), help="Task type to execute")
    parser.add_argument("--pr", help="PR number(s), comma-separated for audit")
    parser.add_argument("--list-models", action="store_true", help="List model routing")
    parser.add_argument("--output", help="Save result to file")
    args = parser.parse_args()

    if args.list_models:
        list_models()
        return 0

    if not args.task:
        parser.error("--task required (or use --list-models)")

    # Parse PR numbers
    if args.pr:
        prs = [int(p.strip()) for p in args.pr.split(",")]
    else:
        parser.error("--pr required")

    # Execute task with appropriate model
    if args.task == "compliance-audit":
        result = await task_compliance_audit(prs)
    elif args.task == "fix-trivy":
        result = await task_fix_trivy(prs[0])
    else:
        print(f"Task {args.task} not yet implemented", file=sys.stderr)
        return 1

    # Output result
    print("\n" + "="*80)
    print(f"RESULT ({result['model']})")
    print("="*80 + "\n")
    print(result["content"])

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(result["content"])
        print(f"\n💾 Saved to {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
