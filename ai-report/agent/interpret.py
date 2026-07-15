#!/usr/bin/env python3
"""CLI entry point for the variant interpretation agent.

Wires together: VCF parsing → ReAct agent (or deterministic fallback) →
report generation → output files.

Usage:
    python ai-report/agent/interpret.py \
        --vcf tests/fixtures/tiny_truth.vcf.gz \
        --metrics tests/fixtures/HG002_chr20.metrics.json \
        --backend deterministic \
        --out results/interpretation.json

Exit codes:
    0  = success (all variants classified)
    1  = error (unrecoverable failure)
    42 = all variants classified but with low confidence
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Ensure the ai-report directory is on the path
_SCRIPT_DIR = Path(__file__).resolve().parent
_AI_REPORT_DIR = _SCRIPT_DIR.parent
if str(_AI_REPORT_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_REPORT_DIR))

from agent.deterministic import DeterministicInterpreter
from agent.llm import create_backend
from agent.react import ReActAgent, Variant
from agent.report import (
    build_report,
    enforce_report_guardrails,
    render_json,
    render_report,
)
from agent.vcf_parser import parse_vcf

logger = logging.getLogger(__name__)


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Variant Interpretation Agent — classify variants using ACMG/AMP criteria",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Deterministic mode (no LLM, CI-safe):
  python ai-report/agent/interpret.py \\
      --vcf tests/fixtures/tiny_truth.vcf.gz \\
      --backend deterministic

  # With Ollama local LLM:
  python ai-report/agent/interpret.py \\
      --vcf results/HG002_chr20/called/HG002_chr20.vcf.gz \\
      --metrics results/HG002_chr20/metrics.json \\
      --backend ollama

  # With OpenAI (requires OPENAI_API_KEY):
  python ai-report/agent/interpret.py \\
      --vcf results/called.vcf.gz \\
      --backend openai \\
      --out results/interpretation.json

Exit codes:
  0  = success
  1  = error
  42 = classified with low confidence
        """,
    )

    parser.add_argument(
        "--vcf",
        required=True,
        help="Path to VCF file (.vcf or .vcf.gz)",
    )
    parser.add_argument(
        "--metrics",
        help="Path to metrics.json (for provenance context)",
    )
    parser.add_argument(
        "--backend",
        choices=["ollama", "openai", "anthropic", "deterministic", "fallback"],
        default="deterministic",
        help="LLM backend to use (default: deterministic)",
    )
    parser.add_argument(
        "--out",
        help="Output path for JSON report (default: stdout text report)",
    )
    parser.add_argument(
        "--out-text",
        help="Output path for text report",
    )
    parser.add_argument(
        "--max-variants",
        type=int,
        default=50,
        help="Maximum variants to interpret (default: 50)",
    )
    parser.add_argument(
        "--genes",
        nargs="+",
        help="Filter to specific genes",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Max agent iterations per variant (default: 10)",
    )
    parser.add_argument(
        "--run-id",
        help="Pipeline run ID for provenance",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON to stdout (instead of text)",
    )

    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    return run_interpretation(args)


def run_interpretation(args: argparse.Namespace) -> int:
    """Execute the interpretation pipeline.

    Steps:
    1. Parse VCF → extract variants
    2. Run agent (ReAct or deterministic) on each variant
    3. Build report with guardrails
    4. Write output files
    """
    start_time = time.perf_counter()

    # ── Step 1: Parse VCF ──────────────────────────────────────────────────
    logger.info(f"Parsing VCF: {args.vcf}")
    try:
        variants = parse_vcf(
            path=args.vcf,
            max_variants=args.max_variants,
            pass_only=True,
            genes=args.genes,
        )
    except FileNotFoundError as e:
        logger.error(f"VCF file not found: {e}")
        return 1
    except ValueError as e:
        logger.error(f"Invalid VCF format: {e}")
        return 1

    if not variants:
        logger.warning("No PASS variants found in VCF")
        print("No PASS variants found in the VCF file.", file=sys.stderr)
        return 1

    logger.info(f"Extracted {len(variants)} variant(s) for interpretation")

    # ── Step 2: Run interpretation ─────────────────────────────────────────
    logger.info(f"Backend: {args.backend}")
    results = []

    if args.backend == "deterministic":
        # Pure deterministic path — no LLM
        interpreter = DeterministicInterpreter()
        results = interpreter.run_batch(variants)
        backend_label = "deterministic-fallback"
    else:
        # ReAct agent with specified backend
        backend = create_backend(args.backend)
        agent = ReActAgent(
            backend=backend,
            max_iterations=args.max_iterations,
        )
        results = agent.run_batch(variants)
        backend_label = backend.model_id

        # For any variant where the agent failed, run deterministic fallback
        fallback = DeterministicInterpreter()
        for i, result in enumerate(results):
            if result.fallback_triggered and result.classification == "Uncertain Significance":
                logger.info(f"Fallback triggered for {result.variant}, running deterministic")
                fallback_result = fallback.run(result.variant)
                # Keep the original trace but use fallback classification
                fallback_result.trace = result.trace + fallback_result.trace
                results[i] = fallback_result

    # ── Step 3: Build report ───────────────────────────────────────────────
    run_id = args.run_id or f"interp_{int(time.time())}"
    report = build_report(
        results=results,
        backend_used=backend_label,
        run_id=run_id,
        vcf_path=args.vcf,
        metrics_path=args.metrics or "",
    )

    # Validate guardrails
    violations = enforce_report_guardrails(report)
    if violations:
        logger.warning(f"Guardrail violations detected: {violations}")

    # ── Step 4: Output ─────────────────────────────────────────────────────
    # JSON output
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        json_output = render_json(report)
        with open(out_path, "w") as f:
            json.dump(json_output, f, indent=2)
        logger.info(f"JSON report written to: {out_path}")

    # Text output
    text_output = render_report(report)
    if args.out_text:
        text_path = Path(args.out_text)
        text_path.parent.mkdir(parents=True, exist_ok=True)
        with open(text_path, "w") as f:
            f.write(text_output)
        logger.info(f"Text report written to: {text_path}")

    # Stdout output
    if args.json:
        json_output = render_json(report)
        print(json.dumps(json_output, indent=2))
    elif not args.out:
        # Print text report to stdout if no file output specified
        print(text_output)

    # ── Summary ────────────────────────────────────────────────────────────
    elapsed = (time.perf_counter() - start_time) * 1000
    n_low_confidence = sum(1 for r in results if r.confidence == "low")

    logger.info(
        json.dumps({
            "action": "interpretation_complete",
            "run_id": run_id,
            "n_variants": len(variants),
            "backend": backend_label,
            "elapsed_ms": round(elapsed, 1),
            "classifications": {r.classification: 0 for r in results},
        })
    )

    # Log classification summary
    counts: dict[str, int] = {}
    for r in results:
        counts[r.classification] = counts.get(r.classification, 0) + 1
    logger.info(f"Classifications: {counts}")

    # Exit codes
    if n_low_confidence == len(results):
        return 42  # All low confidence
    return 0


if __name__ == "__main__":
    sys.exit(main())
