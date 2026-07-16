"""Chatbot page — LLM-powered conversational interface over pipeline data.

This module implements a clinical genomics pipeline assistant that can answer
questions about runs, QC metrics, validation results, and operational trends.

Architecture:
  1. If Ollama is running locally, the bot uses an LLM (mistral/llama3) with
     a system prompt containing the pipeline data context. This gives natural,
     flexible answers to arbitrary questions.
  2. If Ollama is unavailable, it falls back gracefully to pattern-matching
     with pandas queries — still useful, just less conversational.

The LLM is given the full dataset summary as context and uses a ReAct-style
tool-calling pattern to query specific data points on demand.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd
import streamlit as st

from demo.data_loader import get_summary_stats, load_all_data

# ── Ollama LLM integration ────────────────────────────────────────────────────


def _check_ollama_available() -> bool:
    """Check if Ollama is running and accessible."""
    try:
        import httpx

        resp = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


def _get_available_models() -> list[str]:
    """Get list of models available in Ollama."""
    try:
        import httpx

        resp = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        if resp.status_code == 200:
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return []


# Preferred models in priority order
_PREFERRED_MODELS = [
    "mistral",
    "llama3",
    "llama3.1",
    "llama2",
    "gemma",
    "phi3",
    "qwen2",
]


def _select_model(available: list[str]) -> str | None:
    """Select the best available model from the preferred list."""
    for pref in _PREFERRED_MODELS:
        for avail in available:
            if pref in avail.lower():
                return avail
    # Fall back to first available
    return available[0] if available else None


def _build_system_prompt(df: pd.DataFrame) -> str:
    """Build a system prompt with full data context for the LLM."""
    stats = get_summary_stats(df)

    # Build a concise but complete data summary
    runs_detail = []
    for _, row in df.iterrows():
        status = "PASS" if row["validation_pass"] else "FAIL"
        runs_detail.append(
            f"  - {row['run_id']}: sample={row['sample_id']}, "
            f"version={row['pipeline_version']}, caller={row['caller']}, "
            f"F1={row['snp_f1']:.4f}, precision={row['snp_precision']:.4f}, "
            f"recall={row['snp_recall']:.4f}, dup={row['percent_duplication']:.3f}, "
            f"variants={row['n_variants']}, turnaround={row['turnaround_min']:.1f}min, "
            f"status={status}"
        )

    runs_text = "\n".join(runs_detail)

    return f"""You are a Clinical Genomics Pipeline Assistant. You help lab directors,
bioinformaticians, and quality managers understand pipeline operational data.

You have access to the following pipeline run data:

SUMMARY:
- Total runs: {stats['total_runs']}
- Samples: {', '.join(stats['samples'])}
- Callers: {', '.join(stats['callers'])}
- Pipeline versions: {', '.join(stats['versions'])}
- Validation pass rate: {stats['pass_rate_pct']}%
- Mean SNP F1: {stats['mean_snp_f1']:.4f}
- Mean turnaround: {stats['mean_turnaround_min']} minutes

DETAILED RUNS:
{runs_text}

DOMAIN CONTEXT:
- SNP F1 is the harmonic mean of precision and recall for SNP variant calls
- Clinical acceptance threshold: F1 >= 0.99
- Validation uses GIAB truth sets (Genome in a Bottle)
- Duplication rate > 8% is concerning (suggests low library complexity)
- Lower turnaround time is better (clinical labs target < 90 min for chr20)
- GATK HaplotypeCaller and DeepVariant are the two variant callers tested
- Pipeline versions 0.2.0 (older) and 0.3.0 (newer, with DeepVariant support)

RESPONSE GUIDELINES:
- Be concise but informative
- Use markdown formatting (bold, tables, bullet points) for readability
- When comparing, provide specific numbers
- Flag any concerning metrics proactively
- If asked to generate a report, include a disclaimer that it requires clinician review
- You can suggest what to look at next based on the data patterns
"""


def _query_ollama(messages: list[dict], model: str) -> str:
    """Send a chat completion request to Ollama."""
    import httpx

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 1024,
        },
    }

    try:
        resp = httpx.post(
            "http://localhost:11434/api/chat",
            json=payload,
            timeout=60.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("message", {}).get("content", "No response generated.")
        else:
            return f"Ollama returned status {resp.status_code}. Falling back to offline mode."
    except Exception as e:
        return f"Error communicating with Ollama: {e}"


def _stream_ollama(messages: list[dict], model: str):
    """Stream a chat completion from Ollama, yielding chunks."""
    import httpx

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": 0.3,
            "num_predict": 1024,
        },
    }

    try:
        with httpx.stream(
            "POST",
            "http://localhost:11434/api/chat",
            json=payload,
            timeout=60.0,
        ) as resp:
            for line in resp.iter_lines():
                if line:
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if data.get("done", False):
                        break
    except Exception as e:
        yield f"\n\n*Error: {e}. Falling back to offline mode.*"


# ── Offline tool functions (fallback when no LLM) ─────────────────────────────


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
        return "All runs **passed** validation (SNP F1 >= 0.99). No failures to report."
    lines = ["Runs that **failed** validation:\n"]
    for _, row in failed.iterrows():
        lines.append(
            f"- `{row['run_id']}`: {row['sample_id']} | "
            f"F1={row['snp_f1']:.4f} | {row['caller']} | v{row['pipeline_version']}"
        )
    lines.append(
        f"\n**{len(failed)} of {len(df)} runs failed** — "
        "these require investigation before results can be clinically reported."
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
        return f"No runs found for sample '{sample}'. Available samples: {available}"
    lines = [f"**Runs for {matches.iloc[0]['sample_id']}:**\n"]
    for _, row in matches.iterrows():
        status = "PASS" if row["validation_pass"] else "FAIL"
        lines.append(
            f"- `{row['run_id']}` | v{row['pipeline_version']} | {row['caller']} | "
            f"F1={row['snp_f1']:.4f} | dup={row['percent_duplication']:.3f} | "
            f"{row['turnaround_min']:.1f} min | {status}"
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
        flag = " ⚠️ (HIGH)" if row["percent_duplication"] > 0.08 else ""
        lines.append(
            f"- {row['sample_id']} (`{row['run_id']}`): "
            f"{row['percent_duplication']*100:.1f}%{flag}"
        )
    mean_dup = df["percent_duplication"].mean()
    lines.append(f"\nMean duplication: **{mean_dup*100:.1f}%**")
    if mean_dup > 0.08:
        lines.append("*Overall duplication is above the 8% concern threshold.*")
    return "\n".join(lines)


def _tool_help(**kwargs: Any) -> str:
    """List what the bot can answer."""
    return (
        "I can answer questions about the clinical genomics pipeline data. "
        "Here are some things you can ask:\n\n"
        "**Summaries & Status**\n"
        "- *What's the overall summary?*\n"
        "- *Are there any failures?*\n"
        "- *Show the last 5 runs*\n\n"
        "**Comparisons**\n"
        "- *Compare GATK vs DeepVariant*\n"
        "- *Compare pipeline versions*\n\n"
        "**Deep Dives**\n"
        "- *Show me details for HG002*\n"
        "- *What are the duplication rates?*\n"
        "- *Which run had the best F1?*\n\n"
        "**Reports**\n"
        "- *Generate a report for HG002_chr20*\n\n"
        "**Tips:** I understand natural language — feel free to ask in your own words. "
        "If Ollama is running locally, I use an LLM for richer answers."
    )


# ── Intent matching (offline fallback) ────────────────────────────────────────

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

_SAMPLE_PATTERN = re.compile(
    r"\b(detail|show|info|about|for)\b.*\b(HG\d+|NA\d+)\w*", re.I
)
_SAMPLE_EXTRACT = re.compile(r"\b(HG\d+\w*|NA\d+\w*)", re.I)
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
    """Generate an offline AI report for a sample."""
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent.parent
    ai_report_dir = repo_root / "ai-report"
    fixtures_dir = repo_root / "tests" / "fixtures"
    metrics_file = fixtures_dir / f"{sample}.metrics.json"

    if metrics_file.exists():
        with open(metrics_file) as fh:
            metrics = json.load(fh)
    else:
        runs = df[df["sample_id"].str.contains(sample, case=False)]
        if runs.empty:
            return f"No data found for sample '{sample}'."
        row = runs.iloc[-1]
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

    try:
        sys.path.insert(0, str(ai_report_dir))
        from infer import enforce_guardrails, render_offline

        report = render_offline(metrics)
        report = enforce_guardrails(report, metrics)
        return f"**AI-Generated Report (offline mode):**\n\n```\n{report}\n```"
    except ImportError:
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
            f"⚠️ AI-DRAFTED — REQUIRES CLINICIAN REVIEW\n\n"
            f"Sample {metrics.get('sample','?')} was processed with the "
            f"{prov.get('caller','?')} variant caller (pipeline "
            f"v{prov.get('pipeline_version','?')}). {verdict}\n\n"
            f"- SNP Precision: {snp.get('precision','n/a')}\n"
            f"- SNP Recall: {snp.get('recall','n/a')}\n"
            f"- SNP F1: {snp.get('f1','n/a')}\n"
            f"- Reference: {prov.get('reference_build','?')}\n"
            f"- Truth set: {prov.get('truth_version','?')}\n"
        )


def _match_intent_offline(user_msg: str, df: pd.DataFrame) -> str:
    """Match user message to an intent and execute (offline fallback)."""
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
            kwargs: dict[str, Any] = {}
            if "df" in tool_fn.__code__.co_varnames:
                kwargs["df"] = df
            kwargs.update(extra_kwargs)

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

    return (
        "I'm not sure how to answer that in offline mode. "
        "Try one of these:\n\n"
        "- *What's the overall summary?*\n"
        "- *Compare callers* or *Compare versions*\n"
        "- *Show failures* or *Show duplication rates*\n"
        "- *Details for HG002*\n\n"
        "💡 **Tip:** Start Ollama locally (`ollama serve`) for "
        "natural-language understanding of arbitrary questions."
    )


# ── Page render ───────────────────────────────────────────────────────────────


def render() -> None:
    """Render the chatbot page."""
    st.markdown(
        '<p class="hero-title" style="font-size:1.8rem;">Pipeline Data Assistant</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="hero-subtitle" style="font-size:0.95rem;">'
        "Ask questions about pipeline runs, QC metrics, and validation results. "
        "Supports LLM mode (Ollama) or offline pattern matching."
        "</p>",
        unsafe_allow_html=True,
    )

    # Suggested prompts
    with st.expander("💡 Example prompts", expanded=False):
        cols = st.columns(3)
        suggestions = [
            "What's the overall summary?",
            "Compare GATK vs DeepVariant",
            "Show me details for HG002",
            "Are there any failures?",
            "Compare pipeline versions",
            "Generate a report for HG002_chr20",
            "Show the last 5 runs",
            "Which run had the best F1?",
            "What are the duplication rates?",
        ]
        for i, suggestion in enumerate(suggestions):
            with cols[i % 3]:
                st.code(suggestion, language=None)

    # Load data
    df = load_all_data()

    # Check Ollama availability
    ollama_available = _check_ollama_available()
    model_name = None

    if ollama_available:
        available_models = _get_available_models()
        model_name = _select_model(available_models)

    # Status indicator
    col_status, col_model = st.columns([2, 3])
    with col_status:
        if ollama_available and model_name:
            st.success("LLM Mode — powered by Ollama", icon="🧠")
        else:
            st.info("Offline Mode — pattern matching", icon="📋")
    with col_model:
        if model_name:
            st.caption(f"Model: `{model_name}` | Temperature: 0.3")
        else:
            st.caption(
                "Start Ollama for LLM mode: `ollama serve` then `ollama pull mistral`"
            )

    st.divider()

    # Initialize chat history
    if "chat_messages" not in st.session_state:
        welcome = (
            "Hello! I'm the **Clinical Genomics Pipeline Assistant**. "
            "I have access to all pipeline run data — QC metrics, validation "
            "results, turnaround times, and variant calling benchmarks.\n\n"
        )
        if ollama_available and model_name:
            welcome += (
                "I'm running in **LLM mode** — ask me anything in natural language "
                "and I'll reason about the data to give you a thoughtful answer.\n\n"
            )
        else:
            welcome += (
                "I'm running in **offline mode** (no Ollama detected). I can still "
                "answer structured questions about the data.\n\n"
            )
        welcome += (
            "**Try asking:**\n"
            "- *What's the overall summary?*\n"
            "- *Compare GATK vs DeepVariant*\n"
            "- *Are there any failures I should worry about?*\n"
            "- *Show me details for HG002*\n"
            "- *Generate a report for NA12878_chr20*\n\n"
            "Type **help** for the full list of capabilities."
        )
        st.session_state.chat_messages = [
            {"role": "assistant", "content": welcome}
        ]

    # Display chat history
    for msg in st.session_state.chat_messages:
        avatar = "🧬" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    # Chat input
    if user_input := st.chat_input("Ask about pipeline data..."):
        # Show user message
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Generate response
        with st.chat_message("assistant"):
            if ollama_available and model_name:
                # LLM mode: stream response from Ollama
                system_prompt = _build_system_prompt(df)
                messages = [{"role": "system", "content": system_prompt}]

                # Add conversation history (last 10 messages for context window)
                history = st.session_state.chat_messages[-10:]
                for msg in history:
                    if msg["role"] in ("user", "assistant"):
                        messages.append(
                            {"role": msg["role"], "content": msg["content"]}
                        )

                # Stream the response
                response_placeholder = st.empty()
                full_response = ""
                try:
                    for chunk in _stream_ollama(messages, model_name):
                        full_response += chunk
                        response_placeholder.markdown(full_response + "▌")
                    response_placeholder.markdown(full_response)
                except Exception:
                    # Fallback to offline on any streaming error
                    full_response = _match_intent_offline(user_input, df)
                    response_placeholder.markdown(full_response)

                response = full_response
            else:
                # Offline mode: pattern matching
                with st.spinner("Querying pipeline data..."):
                    response = _match_intent_offline(user_input, df)
                st.markdown(response)

        st.session_state.chat_messages.append(
            {"role": "assistant", "content": response}
        )
