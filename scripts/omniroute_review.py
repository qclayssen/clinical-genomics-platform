#!/usr/bin/env python3
"""Multi-model specialist review of this repo's changes via a local OmniRoute gateway.

Dispatches changed files to a small panel of LLM "specialists", each scoped to one
part of this platform's non-negotiables (provenance/append-only, AI guardrails,
digest-pinned containers, hap.py-vs-GIAB validation, CDK guardrail invariants,
ADR append-only convention). Talks to OmniRoute's OpenAI-compatible endpoint —
nothing here calls a provider directly, and no repo file ever holds a provider key.

Prerequisites (one-time, outside this repo):
    npm install -g omniroute
    mkdir -p ~/.omniroute && cp .env.example ~/.omniroute/.env
    # then set, at minimum, in ~/.omniroute/.env:
    #   JWT_SECRET=$(openssl rand -base64 48)
    #   API_KEY_SECRET=$(openssl rand -hex 32)
    #   STORAGE_ENCRYPTION_KEY=$(openssl rand -hex 32)   # else API keys sit in plaintext SQLite
    #   INPUT_SANITIZER_MODE=block                        # default is warn-only (fail-open)
    #   REQUIRE_API_KEY=true
    omniroute   # dashboard + gateway on http://localhost:20128
    # then in the dashboard: Providers > connect free-tier accounts (Kiro gives
    # Qwen3-Coder + DeepSeek; Kimi Coding gives Kimi-Thinking) — check what's
    # already connected first with `omniroute providers list`

Usage:
    export OMNIROUTE_API_KEY=...   # Dashboard > Settings > API Keys (REQUIRE_API_KEY=true)
    python scripts/omniroute_review.py pipeline/main.nf infra/lib/data-lake-stack.ts
    python scripts/omniroute_review.py --tier balanced $(git diff --name-only main)
"""
import argparse
import asyncio
import fnmatch
import json
import os
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent

# Each specialist targets one of this platform's real non-negotiables (see CLAUDE.md),
# not a generic checklist — "free" is the default tier; --tier balanced/premium swaps
# in the paid model where domain judgment (not syntax) is what's being reviewed.
SPECIALISTS = {
    "nextflow": {
        "icon": "📜",
        "globs": ["pipeline/modules/**/*.nf", "pipeline/main.nf", "*.nf", "nextflow.config"],
        "free": "kiro/qwen3-coder-next",
        "balanced": "kiro/qwen3-coder-next",
        "premium": "claude/claude-opus-4-8",
        "prompt": """Role: Senior Nextflow DSL2 reviewer for a clinical genomics pipeline.

This repo's convention (nf-core style, one process per file): every module needs a
`stub:` block with the same output filenames as `script:` (so `-stub` resolves the
DAG offline), a digest-pinned `container` directive, and metrics that matter must be
joined into the JSON_METRICS(...) input in main.nf rather than emitted on a side
channel that skips the provenance stamp.

Review the code below against those three rules plus general DSL2 correctness
(channel type matching, resource allocation, error handling):

```
{code}
```

Provide: strengths, issues by severity (critical/medium/minor), and a verdict —
READY / NEEDS_REVISION / BLOCKED.""",
    },
    "provenance": {
        "icon": "🔒",
        "globs": ["db/schema.sql", "pipeline/bin/build_metrics.py", "pipeline/bin/ingest_metrics.py", "db/migrations/**"],
        "free": "kimi-coding/kimi-k2.6-thinking",
        "balanced": "kimi-coding/kimi-k2.6-thinking",
        "premium": "codex/gpt-5.6-terra",
        "prompt": """Role: Reviewer for an insert-only provenance system.

This platform's rule: a correction is a *new* record, never an edit. DynamoDB is the
primary store (append-only enforced by IAM deny of DeleteItem/UpdateItem); the
Postgres read-replica tables still carry `forbid_mutation()` triggers. No field is
ever removed from the metrics.json provenance stamp (git commit, tool/reference/
truth-set versions, SHA-256 checksums of every input).

Review the code below for anything that adds an update/delete path, silently drops a
provenance field, or otherwise weakens append-only-ness:

```
{code}
```

Provide: what's correct, any violation found (with line reference), and a verdict —
SAFE / VIOLATION_FOUND.""",
    },
    "validation": {
        "icon": "🧬",
        "globs": ["pipeline/modules/validate/**", "docs/VALIDATION.md", "pipeline/bin/build_metrics.py", "**/*happy*"],
        "free": "kiro/deepseek-3.2",
        "balanced": "gemini/gemini-2.5-pro",
        "premium": "gemini/gemini-2.5-pro",
        "prompt": """Role: Genomics validation reviewer for a GIAB-benchmarked SNV caller.

This platform's rule: SNV calls are benchmarked with hap.py (xcmp engine, not
vcfeval — the pinned container lacks rtg-tools) against GIAB HG002 v4.2.1 truth,
restricted to the high-confidence chr20 BED. Acceptance criterion is SNV F1 >= 0.99;
below-threshold runs must be flagged and withheld from reporting, and any change to
reference/caller/filtering must re-trigger validation before a version is tagged.

Review the code/docs below for correctness of the hap.py invocation, threshold
handling, and whether a change here should have triggered re-validation but didn't:

```
{code}
```

Provide: validation-methodology assessment, risks, and a verdict —
READY / NEEDS_REVALIDATION / BLOCKED.""",
    },
    "infra": {
        "icon": "☁️",
        "globs": ["infra/lib/**/*.ts", "infra/bin/**/*.ts", "lambdas/**/*.py"],
        "free": "kiro/qwen3-coder-next",
        "balanced": "claude/claude-opus-4-8",
        "premium": "claude/claude-opus-4-8",
        "prompt": """Role: AWS Solutions Architect reviewing CDK/Lambda code for a clinical-data platform.

This repo's CDK guardrail tests (infra/test/stacks.test.ts) encode accreditation-
relevant invariants that must stay true: bucket versioning, S3 public-access block,
TLS-only, and IAM deny-delete on raw/results buckets and the DynamoDB table.

Review the code below for anything that would violate one of those invariants, plus
general Lambda/Batch/S3/DynamoDB/EventBridge correctness and cost:

```
{code}
```

Provide: architecture assessment, any guardrail violation found, cost notes, and a
verdict — SAFE / GUARDRAIL_AT_RISK.""",
    },
    "ai_guardrails": {
        "icon": "🤖",
        "globs": ["ai-report/infer.py", "ai-report/agent/**/*.py", "ai-report/prompts/**"],
        "free": "kimi-coding/kimi-k2.6-thinking",
        "balanced": "codex/gpt-5.6-terra",
        "premium": "codex/gpt-5.6-terra",
        "prompt": """Role: Reviewer for an AI-output guardrail system in a clinical-adjacent tool.

This platform's rule (ADR-0008): every AI-drafted report passes through
enforce_guardrails() before output — it must re-insert the "AI-DRAFTED — REQUIRES
CLINICIAN REVIEW" banner if missing, guarantee a Provenance: line, and scrub advice
phrasing ("we recommend", "diagnos...", "treat... with") to "[review required]". The
model only ever sees metrics.json, never raw reads or VCF body.

Review the code below for any path that could produce output without going through
enforce_guardrails(), or that weakens the banner/provenance/scrub behavior:

```
{code}
```

Provide: guardrail coverage assessment, any bypass found, and a verdict —
SAFE / BYPASS_FOUND.""",
    },
    "adr": {
        "icon": "📋",
        "globs": ["docs/adr/**/*.md"],
        "free": "kimi-coding/kimi-k2.6-thinking",
        "balanced": "kimi-coding/kimi-k2.6-thinking",
        "premium": "claude/claude-opus-4-7",
        "prompt": """Role: Reviewer for an append-only architecture-decision-record process.

This repo's rule: ADRs are numbered sequentially in docs/adr/, never renumbered or
rewritten in place. Changing a past decision means adding a *new* ADR that
supersedes it and marking the old one's status "Superseded by ADR-XXXX".

Review the change below for: correct next-number usage, whether it edits history
instead of superseding, and whether docs/adr/README.md's index was updated to match:

```
{code}
```

Provide: compliance assessment and a verdict — COMPLIANT / REWRITES_HISTORY.""",
    },
    "data_integrity": {
        "icon": "🛡️",
        "globs": ["docker/**/Dockerfile*", "pipeline/modules/**/*.nf"],
        "free": "kimi-coding/kimi-k2.6-thinking",
        "balanced": "kimi-coding/kimi-k2.6-thinking",
        "premium": "kiro/deepseek-3.2",
        "prompt": """Role: Supply-chain / reproducibility reviewer for a genomics pipeline.

This repo's rule (ADR-0009): production containers are pinned by digest
(`@sha256:...`), one tool per image, biocontainers preferred, and container identity
is captured in provenance. Prototyping-only tags are the one accepted exception.

Review the code below for any container reference that isn't digest-pinned without a
clear prototyping justification, and for input-checksum coverage:

```
{code}
```

Provide: findings and a verdict — PINNED / UNPINNED_FOUND.""",
    },
}

# kiro/kimi-coding/codex route through subscription "coding plan" credits, not raw
# per-token billing, so 0.00 here means "already paid for", not "no cost anywhere".
COST_PER_M = {
    "kiro/qwen3-coder-next": 0.00,
    "kiro/deepseek-3.2": 0.00,
    "kimi-coding/kimi-k2.6-thinking": 0.00,
    "codex/gpt-5.6-terra": 0.00,
    "gemini/gemini-2.5-pro": 1.25,
    "claude/claude-opus-4-8": 2.00,
    "claude/claude-opus-4-7": 2.00,
}


def matches(path: Path, globs: list[str]) -> bool:
    rel = str(path.relative_to(REPO_ROOT)) if path.is_absolute() else str(path)
    return any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(path.name, g) for g in globs)


def gather_specialists(paths: list[Path]) -> dict[str, list[Path]]:
    assigned: dict[str, list[Path]] = {}
    for name, spec in SPECIALISTS.items():
        hit = [p for p in paths if matches(p, spec["globs"])]
        if hit:
            assigned[name] = hit
    return assigned


async def call_specialist(client: httpx.AsyncClient, base_url: str, name: str, model: str, code: str, api_key: str | None) -> dict:
    # OmniRoute always responds as SSE (chat.completion.chunk events), regardless of
    # the "stream" request field, so this reads it as a stream and reassembles the text.
    spec = SPECIALISTS[name]
    prompt = spec["prompt"].format(code=code[:6000])
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    content_parts = []
    cost_cents = None
    async with client.stream(
        "POST",
        f"{base_url}/v1/chat/completions",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "No tools are available. Respond with plain-text review prose only — never emit tool-call or file-read syntax."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        },
        headers=headers,
        timeout=90.0,
    ) as resp:
        resp.raise_for_status()
        header_cost = resp.headers.get("x-omniroute-response-cost")
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[len("data: "):]
            if payload == "[DONE]":
                break
            chunk = json.loads(payload)
            delta = chunk["choices"][0]["delta"].get("content")
            if delta:
                content_parts.append(delta)
    content = "".join(content_parts)
    if header_cost is not None:
        cost_cents = float(header_cost) * 100
    else:
        cost_cents = (len(content) / 4 / 1_000_000) * COST_PER_M.get(model, 1.0) * 100
    return {"name": name, "icon": spec["icon"], "model": model, "content": content, "cost_cents": cost_cents}


async def run(paths: list[Path], tier: str, base_url: str, only: str | None, api_key: str | None) -> int:
    assigned = gather_specialists(paths)
    if only:
        assigned = {k: v for k, v in assigned.items() if k == only}
    if not assigned:
        print("No specialist matched the given paths — nothing to review.")
        return 0

    async with httpx.AsyncClient() as client:
        tasks = []
        for name, files in assigned.items():
            code = "\n\n".join(f"# {f}\n{f.read_text(errors='replace')}" for f in files)
            model = SPECIALISTS[name][tier]
            tasks.append(call_specialist(client, base_url, name, model, code, api_key))

        try:
            results = await asyncio.gather(*tasks)
        except httpx.ConnectError:
            print(f"Could not reach OmniRoute at {base_url} — is `omniroute` running?", file=sys.stderr)
            return 1
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                print("Unauthorized — set OMNIROUTE_API_KEY or pass --api-key (Dashboard > Settings > API Keys).", file=sys.stderr)
            else:
                print(f"OmniRoute returned an error: {e}", file=sys.stderr)
            return 1

    total_cost = 0.0
    for r in results:
        total_cost += r["cost_cents"]
        print(f"\n{r['icon']}  {r['name'].replace('_', ' ').upper()}  ({r['model']}, ${r['cost_cents'] / 100:.3f})")
        print("-" * 60)
        print(r["content"])
    print(f"\nTotal estimated cost: ${total_cost / 100:.3f}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", type=Path, help="Files to review (e.g. output of `git diff --name-only`)")
    parser.add_argument("--tier", choices=["free", "balanced", "premium"], default="free")
    parser.add_argument("--specialist", choices=list(SPECIALISTS), default=None, help="Run only this specialist")
    parser.add_argument("--base-url", default="http://localhost:20128")
    parser.add_argument("--api-key", default=os.environ.get("OMNIROUTE_API_KEY"), help="OmniRoute API key (or set OMNIROUTE_API_KEY)")
    args = parser.parse_args()

    existing = [p for p in args.paths if p.is_file()]
    missing = [p for p in args.paths if not p.is_file()]
    if missing:
        print(f"Skipping missing paths: {missing}", file=sys.stderr)
    if not existing:
        print("No existing files given.", file=sys.stderr)
        return 1

    return asyncio.run(run(existing, args.tier, args.base_url, args.specialist, args.api_key))


if __name__ == "__main__":
    sys.exit(main())
