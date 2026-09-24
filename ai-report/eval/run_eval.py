#!/usr/bin/env python3
"""Agent evaluation harness — "hap.py for the LLM" (ADR-0032).

Runs the variant-interpretation agent over the committed gold set and reports
classification accuracy (5-class + collapsed 3-class), per-class accuracy,
confusion matrices, hallucinated-citation rate and tool-grounding rate, gated
against ``eval_config.json``. The JSON report is provenance-stamped (git commit,
gold-set / config / KB SHA-256, backend + model id).

Default backend is ``deterministic`` (the scripted ReAct backend in
``agent/llm.py``): offline, no GPU/network, reproducible — suitable for CI.
Any other backend ``create_backend()`` supports can be selected with
``--backend``; ``interpreter`` runs the no-LLM ``DeterministicInterpreter``
directly.

Usage:
    python ai-report/eval/run_eval.py
    python ai-report/eval/run_eval.py --backend anthropic --out results/agent_eval/anthropic.json

Exit codes: 0 = all gates pass, 1 = a gate failed, 2 = harness error.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional

_EVAL_DIR = Path(__file__).resolve().parent
_AI_REPORT_DIR = _EVAL_DIR.parent
_REPO_ROOT = _AI_REPORT_DIR.parent
for _p in (_AI_REPORT_DIR, _EVAL_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import eval_metrics as M  # noqa: E402
from agent.data.knowledge_base import _DEFAULT_DB, KnowledgeBase  # noqa: E402
from agent.deterministic import DeterministicInterpreter  # noqa: E402
from agent.llm import create_backend  # noqa: E402
from agent.react import ReActAgent, Variant  # noqa: E402

DEFAULT_GOLD = _EVAL_DIR / "gold_set.jsonl"
DEFAULT_CONFIG = _EVAL_DIR / "eval_config.json"
DEFAULT_OUT = _REPO_ROOT / "results" / "agent_eval" / "report.json"

BACKENDS = ["deterministic", "interpreter", "ollama", "openai", "anthropic",
            "azure_foundry", "bedrock", "fallback"]


# ─── IO / provenance ─────────────────────────────────────────────────────────


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_gold_set(path: Path) -> list[dict]:
    rows = []
    with open(path) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _git(*args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", *args], cwd=_REPO_ROOT, capture_output=True,
                             text=True, timeout=10, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def build_provenance(gold: Path, config: Path, backend: str, model_id: str) -> dict:
    kb = KnowledgeBase()
    try:
        kb_meta = kb.get_metadata()
    finally:
        kb.close()
    status = _git("status", "--porcelain")
    return {
        "git_commit": _git("rev-parse", "HEAD") or "unknown",
        "git_dirty": bool(status) if status is not None else None,
        "gold_set_path": str(gold.resolve().relative_to(_REPO_ROOT)) if gold.resolve().is_relative_to(_REPO_ROOT) else str(gold),
        "gold_set_sha256": sha256_file(gold),
        "config_sha256": sha256_file(config),
        "knowledge_base_sha256": sha256_file(_DEFAULT_DB),
        "knowledge_base_metadata": kb_meta,
        "backend": backend,
        "model_id": model_id,
        "python": platform.python_version(),
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }


# ─── Running the agent ───────────────────────────────────────────────────────


def _variant(row: dict) -> Variant:
    # Gene is deliberately NOT passed: the agent must find it via its tools.
    return Variant(chrom=row["chrom"], pos=int(row["pos"]), ref=row["ref"], alt=row["alt"])


def run_agent(rows: list[dict], backend: str, apply_fallback: bool = True) -> tuple[list[dict], str]:
    """Run the chosen backend over the rows. Returns (result dicts, model_id).

    With ``apply_fallback`` (default, mirrors ``interpret.py`` and the REST API),
    any run that triggered fallback is re-classified by the deterministic
    interpreter, keeping the original trace in front of the fallback trace.
    """
    variants = [_variant(r) for r in rows]
    if backend == "interpreter":
        interp = DeterministicInterpreter()
        return [r.to_dict() for r in interp.run_batch(variants)], "deterministic-interpreter"

    llm = create_backend(backend)
    agent = ReActAgent(backend=llm)
    try:
        results = agent.run_batch(variants)
    finally:
        agent.close()
    if apply_fallback:
        fallback = DeterministicInterpreter()
        for i, res in enumerate(results):
            if res.fallback_triggered:
                fb = fallback.run(res.variant)
                fb.trace = res.trace + fb.trace
                results[i] = fb
    return [r.to_dict() for r in results], llm.model_id


# ─── Evaluation ──────────────────────────────────────────────────────────────


def evaluate(rows: list[dict], results: list[dict], config: dict) -> dict:
    """Score results against rows and evaluate every configured gate."""
    if len(rows) != len(results):
        raise ValueError(f"{len(rows)} gold rows but {len(results)} results")
    cases = [M.score_case(r, res) for r, res in zip(rows, results)]
    all_tiers = sorted({r["tier"] for r in rows})
    by_tier = {t: M.aggregate(cases, [t]) for t in all_tiers}
    gates = []
    for g in config.get("gates", []):
        agg = M.aggregate(cases, g["tiers"])
        failures = M.check_thresholds(agg, g["thresholds"])
        gates.append({"name": g["name"], "tiers": g["tiers"],
                      "thresholds": g["thresholds"], "passed": not failures,
                      "failures": failures})
    return {
        "summary_all": M.aggregate(cases, all_tiers),
        "by_tier": by_tier,
        "gates": gates,
        "passed": all(g["passed"] for g in gates),
        "cases": cases,
    }


def run(gold: Path = DEFAULT_GOLD, config_path: Path = DEFAULT_CONFIG,
        backend: str = "deterministic", apply_fallback: bool = True,
        tiers: Optional[list[str]] = None) -> dict:
    """Run the harness end to end and return the full report dict."""
    config = json.loads(config_path.read_text())
    rows = load_gold_set(gold)
    if tiers:
        rows = [r for r in rows if r["tier"] in tiers]
    results, model_id = run_agent(rows, backend, apply_fallback)
    report = {
        "harness": "agent-eval",
        "harness_version": config.get("harness_version"),
        "provenance": build_provenance(gold, config_path, backend, model_id),
        "gold_set": {
            "n_rows": len(rows),
            "tiers": {t: sum(1 for r in rows if r["tier"] == t) for t in sorted({r["tier"] for r in rows})},
            "expected_class_counts": M.class_counts(rows),
        },
        "scored_result": "final result after deterministic fallback" if apply_fallback
                         else "raw agent result (no fallback)",
        "disclaimer": ("Portfolio evaluation on a small KB-derived gold set. Measures agreement "
                       "with the local ClinVar subset and citation integrity; it is not a "
                       "clinical validation and supports no diagnostic use."),
    }
    report.update(evaluate(rows, results, config))
    report["results"] = results
    return report


def _fmt(x) -> str:
    return "n/a" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))


def print_summary(report: dict) -> None:
    p = report["provenance"]
    print(f"Agent eval — backend={p['backend']} model={p['model_id']} commit={p['git_commit'][:10]}")
    print(f"gold set sha256={p['gold_set_sha256'][:16]}…  rows={report['gold_set']['n_rows']} "
          f"tiers={report['gold_set']['tiers']}")
    for tier, agg in report["by_tier"].items():
        print(f"  [{tier:6}] n={agg['n_cases']:3}  acc5={_fmt(agg['accuracy_5class'])}  "
              f"acc3={_fmt(agg['accuracy_3class'])}  opp.dir.err={agg['opposite_direction_errors']}  "
              f"halluc={_fmt(agg['hallucinated_citation_rate'])}  "
              f"grounding={_fmt(agg['tool_grounding_rate'])}  fallback={_fmt(agg['fallback_rate'])}")
    gold = report["by_tier"].get("gold")
    if gold:
        print("  gold confusion (5-class, rows=expected, cols=predicted):")
        cols = M.CLASSES_5 + [M.INVALID]
        print("        " + " ".join(f"{c:>7}" for c in cols))
        for e, row in gold["confusion_5class"].items():
            print(f"  {e:>5} " + " ".join(f"{row[c]:>7}" for c in cols))
    for g in report["gates"]:
        status = "PASS" if g["passed"] else "FAIL"
        print(f"  gate {g['name']}: {status}" + ("" if g["passed"] else f" — {'; '.join(g['failures'])}"))
    print("OVERALL:", "PASS" if report["passed"] else "FAIL")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate the variant-interpretation agent against the gold set.")
    ap.add_argument("--backend", default="deterministic", choices=BACKENDS)
    ap.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--tiers", nargs="+", help="Restrict to these tiers (gold silver probe)")
    ap.add_argument("--no-fallback", action="store_true",
                    help="Score the raw agent result instead of the post-fallback result")
    args = ap.parse_args(argv)
    try:
        report = run(args.gold, args.config, args.backend,
                     apply_fallback=not args.no_fallback, tiers=args.tiers)
    except Exception as e:  # noqa: BLE001 — surface any harness failure as exit 2
        print(f"harness error: {e}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True, default=sorted) + "\n")
    print_summary(report)
    print(f"report: {args.out}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
