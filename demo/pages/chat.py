"""Chatbot page — conversational interface over pipeline data.

Implements a local, offline-capable chatbot that answers questions about
pipeline runs, QC metrics, and validation results. Uses pattern matching
and pandas queries (no external LLM API required by default).

When Ollama is available locally, the bot upgrades to LLM-powered responses
with the same tool-use pattern as the ReAct variant interpretation agent.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd
import streamlit as st

from demo.data_loader import get_summary_stats, load_all_data

# ── Tool functions (the bot's "actions") ──────────────────────────────────────


def _tool_summary(df: pd.DataFrame, **kwargs: Any) -> str:
    """Provide a high-level summary of all pipeline runs."""
    stats = get_summary_stats(df)
    return (
        f"There are **{stats['total_runs']} runs** across "
        f"{len(stats['samples'])} samples ({', '.join(stats['samples'])}). "
        f"Callers used: {', '.join(stats['callers'])}. "
        f"Pipeline versions: {', '.join(stats['versions'])}.\n\n"
        f"- Validation pass rate: **{stats['pass_rate_pct']}%**\n"
        f"- Mean SNP F1: **{stats['mean_snp_f1']:.4f}**\n"
        f"- Mean turnaround: **{stats['mean_turnaround_min']} min**"
    )


def _tool_best_f1(df: pd.DataFrame, **kwargs: Any) -> str:
    """Find the run(s) with the highest SNP F1."""
    best = df.loc[df["snp_f1"].idxmax()]
    return (
        f"The best SNP F1 is **{best['snp_f1']:.4f}** from run "
        f"`{best['run_id']}` (sample {best['sample_id']}, "
        f"caller {best['caller']}, pipeline {best['pipeline_version']})."
    )


def _tool_worst_f1(df: pd.DataFrame, **kwargs: Any) -> str:
    """Find the run(s) with the lowest SNP F1."""
    worst = df.loc[df["snp_f1"].idxmin()]
    return (
        f"The lowest SNP F1 is **{worst['snp_f1']:.4f}** from run "
        f"`{worst['run_id']}` (sample {worst['sample_id']}, "
        f"caller {worst['caller']}, pipeline {worst['pipeline_version']})."
    )


def _tool_failures(df: pd.DataFrame, **kwargs: Any) -> str:
    """List runs that failed validation (F1 < 0.99)."""
    failed = df[~df["validation_pass"]]
    if failed.empty:
        return "All runs **passed** validation (SNP F1 >= 0.99)."
    lines = ["Runs that **failed** validation:\n"]
    for _, row in failed.iterrows():
        lines.append(
            f"- `{row['run_id']}`: {row['sample_id']} | "
            f"F1={row['snp_f1']:.4f} | {row['caller']} | v{row['pipeline_version']}"
        )
    return "\n".join(lines)


def _tool_compare_callers(df: pd.DataFrame, **kwargs: Any) -> str:
    """Compare GATK vs DeepVariant on key metrics."""
    grouped = df.groupby("caller").agg(
        mean_f1=("snp_f1", "mean"),
        mean_precision=("snp_precision", "mean"),
        mean_recall=("snp_recall", "mean"),
        mean_turnaround=("turnaround_min", "mean"),
        n_runs=("run_id", "count"),
    )
    lines = ["**Caller comparison:**\n"]
    lines.append("| Caller | Runs | Mean F1 | Mean Precision | Mean Recall | Turnaround |")
    lines.append("|--------|------|---------|----------------|-------------|------------|")
    for caller, row in grouped.iterrows():
        lines.append(
            f"| {caller} | {row['n_runs']:.0f} | {row['mean_f1']:.4f} | "
            f"{row['mean_precision']:.4f} | {row['mean_recall']:.4f} | "
            f"{row['mean_turnaround']:.1f} min |"
        )
    return "\n".join(lines)


def _tool_sample_detail(df: pd.DataFrame, sample: str = "", **kwargs: Any) -> str:
    """Show details for a specific sample."""
    if not sample:
        return "Please specify a sample name (e.g., HG002_chr20, HG003_chr20)."
    matches = df[df["sample_id"].str.contains(sample, case=False)]
    if matches.empty:
        available = ", ".join(df["sample_id"].unique())
        return f"No runs found for sample '{sample}'. Available: {available}"
    lines = [f"**Runs for {matches.iloc[0]['sample_id']}:**\n"]
    for _, row in matches.iterrows():
        lines.append(
            f"- `{row['run_id']}` | v{row['pipeline_version']} | {row['caller']} | "
            f"F1={row['snp_f1']:.4f} | dup={row['percent_duplication']:.3f} | "
            f"{row['turnaround_min']:.1f} min"
        )
    return "\n".join(lines)


def _tool_version_compare(df: pd.DataFrame, **kwargs: Any) -> str:
    """Compare pipeline versions on key metrics."""
    grouped = df.groupby("pipeline_version").agg(
        mean_f1=("snp_f1", "mean"),
        mean_dup=("percent_duplication", "mean"),
        mean_turnaround=("turnaround_min", "mean"),
        n_runs=("run_id", "count"),
    )
    lines = ["**Pipeline version comparison:**\n"]
    lines.append("| Version | Runs | Mean F1 | Mean Dup Rate | Turnaround |")
    lines.append("|---------|------|---------|---------------|------------|")
    for ver, row in grouped.iterrows():
        lines.append(
            f"| {ver} | {row['n_runs']:.0f} | {row['mean_f1']:.4f} | "
            f"{row['mean_dup']:.3f} | {row['mean_turnaround']:.1f} min |"
        )
    return "\n".join(lines)


def _tool_last_n_runs(df: pd.DataFrame, n: int = 5, **kwargs: Any) -> str:
    """Show the last N runs."""
    recent = df.sort_values("started_at", ascending=False).head(n)
    lines = [f"**Last {len(recent)} runs:**\n"]
    for _, row in recent.iterrows():
        status = "PASS" if row["validation_pass"] else "FAIL"
        lines.append(
            f"- `{row['run_id']}` ({row['started_at'].strftime('%Y-%m-%d')}) | "
            f"{row['sample_id']} | {row['caller']} | F1={row['snp_f1']:.4f} | {status}"
        )
    return "\n".join(lines)


def _tool_duplication(df: pd.DataFrame, **kwargs: Any) -> str:
    """Report on duplication rates across runs."""
    lines = ["**Duplication rates:**\n"]
    sorted_df = df.sort_values("percent_duplication", ascending=False)
    for _, row in sorted_df.iterrows():
        flag = " (high)" if row["percent_duplication"] > 0.08 else ""
        lines.append(
            f"- {row['sample_id']} (`{row['run_id']}`): "
            f"{row['percent_duplication']*100:.1f}%{flag}"
        )
    mean_dup = df["percent_duplication"].mean()
    lines.append(f"\nMean duplication: **{mean_dup*100:.1f}%**")
    return "\n".join(lines)


def _tool_help(**kwargs: Any) -> str:
    """List what the bot can answer."""
    return (
        "I can answer questions about the pipeline data. Try:\n\n"
        "- *What's the overall summary?*\n"
        "- *Which run had the best F1?*\n"
        "- *Are there any failures?*\n"
        "- *Compare GATK vs DeepVariant*\n"
        "- *Show me details for HG002*\n"
        "- *Compare pipeline versions*\n"
        "- *Show the last 5 runs*\n"
        "- *What are the duplication rates?*\n"
        "- *Generate a report for HG002_chr20*"
    )


# ── Intent matching ───────────────────────────────────────────────────────────

_INTENTS: list[tuple[re.Pattern, str, dict]] = [
    (re.compile(r"\b(summary|overview|overall|how many|status)\b", re.I), "summary", {}),
    (re.compile(r"\b(best|highest|top).*(f1|score|precision)\b", re.I), "best_f1", {}),
    (re.compile(r"\b(worst|lowest|bottom).*(f1|score)\b", re.I), "worst_f1", {}),
    (re.compile(r"\b(fail|failed|failures|didn.t pass)\b", re.I), "failures", {}),
    (re.compile(r"\b(compare|vs|versus).*(caller|gatk|deepvariant)\b", re.I), "compare_callers", {}),
    (re.compile(r"\b(compare|vs|versus).*(version|pipeline)\b", re.I), "version_compare", {}),
    (re.compile(r"\b(version|pipeline).*(compare|vs|versus)\b", re.I), "version_compare", {}),
    (re.compile(r"\b(last|recent|latest)\s*(\d+)?\s*(run)?\b", re.I), "last_n_runs", {}),
    (re.compile(r"\b(dup|duplication)\b", re.I), "duplication", {}),
    (re.compile(r"\b(help|what can you|commands|capabilities)\b", re.I), "help", {}),
]

# Sample-specific queries
_SAMPLE_PATTERN = re.compile(
    r"\b(detail|show|info|about|for)\b.*\b(HG\d+|NA\d+)\w*", re.I
)
_SAMPLE_EXTRACT = re.compile(r"\b(HG\d+\w*|NA\d+\w*)", re.I)

# Report generation
_REPORT_PATTERN = re.compile(
    r"\b(report|generate|draft|summarize|summarise)\b.*\b(HG\d+|NA\d+)\w*", re.I
)

_TOOL_MAP = {
    "summary": _tool_summary,
    "best_f1": _tool_best_f1,
    "worst_f1": _tool_worst_f1,
    "failures": _tool_failures,
    "compare_callers": _tool_compare_callers,
    "version_compare": _tool_version_compare,
    "last_n_runs": _tool_last_n_runs,
    "duplication": _tool_duplication,
    "help": _tool_help,
    "sample_detail": _tool_sample_detail,
}


def _extract_number(text: str, default: int = 5) -> int:
    """Extract a number from the user message (for 'last N runs')."""
    match = re.search(r"\b(\d+)\b", text)
    return int(match.group(1)) if match else default


def _generate_report(df: pd.DataFrame, sample: str) -> str:
    """Generate an offline AI report for a sample (reuses the pipeline's renderer)."""
    import sys
    from pathlib import Path

    # Try to import the actual infer.py renderer
    repo_root = Path(__file__).resolve().parent.parent.parent
    ai_report_dir = repo_root / "ai-report"

    # Find a matching metrics.json fixture
    fixtures_dir = repo_root / "tests" / "fixtures"
    metrics_file = fixtures_dir / f"{sample}.metrics.json"

    if metrics_file.exists():
        with open(metrics_file) as fh:
            metrics = json.load(fh)
    else:
        # Build a synthetic metrics dict from the DataFrame
        runs = df[df["sample_id"].str.contains(sample, case=False)]
        if runs.empty:
            return f"No data found for sample '{sample}'."
        row = runs.iloc[-1]  # Latest run
        metrics = {
            "sample": row["sample_id"],
            "schema_version": "1.0",
            "qc": {"percent_duplication": row["percent_duplication"]},
            "validation": {
                "snp": {
                    "precision": row["snp_precision"],
                    "recall": row["snp_recall"],
                    "f1": row["snp_f1"],
                }
            },
            "validation_pass": bool(row["validation_pass"]),
            "provenance": {
                "pipeline_version": row["pipeline_version"],
                "git_commit": "demo",
                "run_id": row["run_id"],
                "caller": row["caller"],
                "reference_build": "GRCh38.p14",
                "truth_version": "GIAB-v4.2.1",
                "n_variants": int(row["n_variants"]),
            },
        }

    # Use the offline renderer directly (no ML dependencies)
    try:
        sys.path.insert(0, str(ai_report_dir))
        from infer import enforce_guardrails, render_offline

        report = render_offline(metrics)
        report = enforce_guardrails(report, metrics)
        return f"**AI-Generated Report (offline mode):**\n\n```\n{report}\n```"
    except ImportError:
        # Fallback: render inline
        snp = metrics.get("validation", {}).get("snp", {})
        prov = metrics.get("provenance", {})
        passed = metrics.get("validation_pass", False)
        verdict = (
            "The run met the F1 >= 0.99 acceptance threshold."
            if passed
            else "The run did NOT meet the acceptance threshold."
        )
        return (
            f"**Draft Report for {metrics.get('sample', sample)}:**\n\n"
            f"AI-DRAFTED -- REQUIRES CLINICIAN REVIEW\n\n"
            f"Sample {metrics.get('sample','?')} was processed with the "
            f"{prov.get('caller','?')} variant caller. {verdict}\n"
            f"SNP precision {snp.get('precision','n/a')}, "
            f"recall {snp.get('recall','n/a')}, F1 {snp.get('f1','n/a')}.\n"
            f"Provenance: git {prov.get('git_commit','?')}, "
            f"{prov.get('truth_version','?')}."
        )


def _match_intent(user_msg: str, df: pd.DataFrame) -> str:
    """Match user message to an intent and execute the corresponding tool."""

    # Check for report generation request
    report_match = _REPORT_PATTERN.search(user_msg)
    if report_match:
        sample_match = _SAMPLE_EXTRACT.search(user_msg)
        sample = sample_match.group(1) if sample_match else ""
        return _generate_report(df, sample)

    # Check for sample-specific queries
    sample_match = _SAMPLE_PATTERN.search(user_msg)
    if sample_match:
        sample_name = _SAMPLE_EXTRACT.search(user_msg)
        if sample_name:
            return _tool_sample_detail(df, sample=sample_name.group(1))

    # Check standard intents
    for pattern, intent_key, extra_kwargs in _INTENTS:
        if pattern.search(user_msg):
            tool_fn = _TOOL_MAP[intent_key]
            kwargs: dict[str, Any] = {"df": df} if "df" in tool_fn.__code__.co_varnames else {}
            kwargs.update(extra_kwargs)

            # Special handling for last_n_runs
            if intent_key == "last_n_runs":
                kwargs["n"] = _extract_number(user_msg)
                kwargs["df"] = df

            if intent_key == "help":
                return _tool_help()

            return tool_fn(**kwargs)

    # Fallback: check if the message contains a sample name
    sample_in_msg = _SAMPLE_EXTRACT.search(user_msg)
    if sample_in_msg:
        return _tool_sample_detail(df, sample=sample_in_msg.group(1))

    # No match
    return (
        "I'm not sure how to answer that. I can help with pipeline data questions like:\n\n"
        "- Overall summary\n"
        "- Best/worst F1 scores\n"
        "- Failed runs\n"
        "- Caller or version comparisons\n"
        "- Sample-specific details\n"
        "- Generate a report\n\n"
        "Type **help** for more examples."
    )


# ── Page render ───────────────────────────────────────────────────────────────


def render() -> None:
    """Render the chatbot page."""
    st.header("Pipeline Data Chatbot")
    st.caption(
        "Ask questions about pipeline runs, QC metrics, and validation results. "
        "The bot queries the same data shown in the Explorer page. "
        "No external API keys required — runs fully offline."
    )

    # Initialize chat history
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {
                "role": "assistant",
                "content": (
                    "Hi! I'm the Clinical Genomics Pipeline assistant. "
                    "I can answer questions about your pipeline runs, QC metrics, "
                    "and validation results.\n\n"
                    "Try asking:\n"
                    "- *What's the overall summary?*\n"
                    "- *Compare GATK vs DeepVariant*\n"
                    "- *Show me details for HG002*\n"
                    "- *Generate a report for HG002_chr20*\n\n"
                    "Type **help** for more options."
                ),
            }
        ]

    # Load data once
    df = load_all_data()

    # Display chat history
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if user_input := st.chat_input("Ask about pipeline data..."):
        # Show user message
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Generate response
        with st.chat_message("assistant"):
            with st.spinner("Querying pipeline data..."):
                response = _match_intent(user_input, df)
            st.markdown(response)

        st.session_state.chat_messages.append(
            {"role": "assistant", "content": response}
        )
