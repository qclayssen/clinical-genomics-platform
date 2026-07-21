"""Variant Interpretation page — surfaces the ReAct interpretation agent.

The agent in ai-report/agent/ does the actual clinical reasoning: it looks a
variant up in ClinVar and gnomAD, pulls gene context, applies ACMG evidence
codes, and drafts a guardrailed report. This page makes that reasoning visible
one step at a time, because the reasoning is the interesting part — a table of
final classifications hides exactly the work worth showing.

Backend policy: the deterministic interpreter is the default, not a fallback.
It needs no LLM, no network, and no setup, so the page behaves identically on a
laptop and in a container. Ollama, when present, is an upgrade.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st

# The agent package lives under ai-report/, which isn't a package root itself.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_AI_REPORT = _REPO_ROOT / "ai-report"
if str(_AI_REPORT) not in sys.path:
    sys.path.insert(0, str(_AI_REPORT))

from agent.data.knowledge_base import KnowledgeBase  # noqa: E402
from agent.deterministic import DeterministicInterpreter  # noqa: E402
from agent.report import (  # noqa: E402
    build_report,
    enforce_report_guardrails,
    render_report,
)
from agent.vcf_parser import parse_vcf  # noqa: E402

_DEFAULT_VCF = _REPO_ROOT / "tests" / "fixtures" / "tiny_truth.vcf"

# ACMG codes starting with B are benign evidence, P are pathogenic. Colour by
# direction so the chips read at a glance without needing the legend.
_BENIGN_PREFIX = "B"

_CLASSIFICATION_COLOURS = {
    "Pathogenic": ("#7F1D1D", "#FCA5A5"),
    "Likely Pathogenic": ("#7C2D12", "#FDBA74"),
    "Uncertain Significance": ("#374151", "#D1D5DB"),
    "Likely Benign": ("#14532D", "#86EFAC"),
    "Benign": ("#064E3B", "#6EE7B7"),
}

_STEP_ICONS = {
    "thought": "💭",
    "action": "🔧",
    "observation": "📋",
    "answer": "✅",
    "error": "⚠️",
}


# ── Data loading ──────────────────────────────────────────────────────────────


@st.cache_resource(show_spinner=False)
def _load_knowledge_base() -> KnowledgeBase:
    """The SQLite KB is read-only and shared across sessions."""
    return KnowledgeBase()


@st.cache_data(show_spinner=False)
def _interpret_all(vcf_path: str) -> list[dict]:
    """Parse the VCF and run every variant through the interpreter.

    Cached because the deterministic run is identical every time — the whole
    point of it — so re-running on each rerender only costs latency.
    """
    kb = _load_knowledge_base()
    variants = parse_vcf(vcf_path, max_variants=50, kb=kb)
    results = DeterministicInterpreter(kb=kb).run_batch(variants)
    return [r.to_dict() for r in results]


# ── Rendering helpers ─────────────────────────────────────────────────────────


def _classification_badge(classification: str) -> str:
    bg, fg = _CLASSIFICATION_COLOURS.get(classification, ("#374151", "#D1D5DB"))
    return (
        f'<span style="background:{bg};color:{fg};padding:0.25rem 0.7rem;'
        f'border-radius:999px;font-size:0.8rem;font-weight:600;">'
        f"{classification}</span>"
    )


def _evidence_chips(codes: list[str]) -> str:
    if not codes:
        return '<span style="color:#6B7280;font-size:0.85rem;">No evidence codes</span>'

    chips = []
    for code in codes:
        if code.startswith(_BENIGN_PREFIX):
            bg, fg = "#064E3B", "#6EE7B7"
        else:
            bg, fg = "#7F1D1D", "#FCA5A5"
        chips.append(
            f'<span style="background:{bg};color:{fg};padding:0.2rem 0.6rem;'
            f'border-radius:6px;font-family:monospace;font-size:0.8rem;'
            f'margin-right:0.35rem;">{code}</span>'
        )
    return "".join(chips)


def _render_trace_step(step: dict) -> None:
    """One reasoning step: what the agent thought, did, and saw."""
    icon = _STEP_ICONS.get(step.get("type", ""), "•")
    step_type = step.get("type", "step").title()
    tool = step.get("tool_name", "")

    header = f"{icon} **{step_type}**"
    if tool:
        header += f" · `{tool}`"

    st.markdown(header)
    content = step.get("content", "")
    if content:
        st.markdown(
            f'<div style="color:#9CA3AF;font-size:0.88rem;margin:0 0 0.6rem 1.6rem;'
            f'border-left:2px solid #2D3348;padding-left:0.8rem;">{content}</div>',
            unsafe_allow_html=True,
        )

    if step.get("tool_output"):
        with st.expander("Tool output", expanded=False):
            st.json(step["tool_output"])


# ── Page render ───────────────────────────────────────────────────────────────


def render() -> None:
    st.markdown(
        '<div class="hero-title">Variant Interpretation</div>'
        '<div class="hero-subtitle">Watch the agent reason from a raw VCF record '
        "to an ACMG classification — one tool call at a time.</div>",
        unsafe_allow_html=True,
    )

    if not _DEFAULT_VCF.exists():
        st.error(f"Fixture VCF not found: `{_DEFAULT_VCF}`")
        return

    try:
        results = _interpret_all(str(_DEFAULT_VCF))
    except FileNotFoundError as exc:
        # The KB is committed, so this means a broken checkout rather than a
        # missing optional dependency — say so instead of degrading silently.
        st.error(f"Knowledge base unavailable — {exc}")
        return

    if not results:
        st.warning("No variants passed the parser filters.")
        return

    st.caption(
        f"Backend: **deterministic** (no LLM required) · "
        f"{len(results)} variants · source: `{_DEFAULT_VCF.relative_to(_REPO_ROOT)}`"
    )

    # ── Summary counts ────────────────────────────────────────────────────────
    counts: dict[str, int] = {}
    for r in results:
        counts[r["classification"]] = counts.get(r["classification"], 0) + 1

    cols = st.columns(len(counts))
    for col, (name, n) in zip(cols, sorted(counts.items())):
        col.metric(name, n)

    st.divider()

    # ── Variant picker ────────────────────────────────────────────────────────
    labels = [
        f"{r['variant']['chrom']}:{r['variant']['pos']} "
        f"{r['variant']['ref']}>{r['variant']['alt']}"
        f"  ({r['variant'].get('gene') or '—'})  —  {r['classification']}"
        for r in results
    ]

    choice = st.radio(
        "Select a variant to interpret",
        options=range(len(results)),
        format_func=lambda i: labels[i],
        index=0,
    )
    selected = results[choice]

    st.divider()

    left, right = st.columns([1, 1], gap="large")

    with left:
        st.subheader("Reasoning trace")
        steps = selected.get("trace", [])
        if not steps:
            st.info("This variant produced no trace steps.")
        else:
            # Replay on demand rather than on every rerender — the animation is
            # the point on first view, but it gets tedious when you're comparing
            # variants back and forth.
            replay = st.button("▶ Replay step by step", key=f"replay_{choice}")
            placeholder = st.container()
            with placeholder:
                for i, step in enumerate(steps):
                    _render_trace_step(step)
                    if replay and i < len(steps) - 1:
                        time.sleep(0.45)

    with right:
        st.subheader("Classification")
        st.markdown(_classification_badge(selected["classification"]), unsafe_allow_html=True)

        st.markdown("**ACMG evidence**")
        st.markdown(_evidence_chips(selected.get("evidence_codes", [])), unsafe_allow_html=True)

        st.markdown(
            f"<div style='color:#9CA3AF;font-size:0.85rem;margin-top:0.8rem;'>"
            f"Confidence: <strong>{selected.get('confidence', 'unknown')}</strong></div>",
            unsafe_allow_html=True,
        )

        if selected.get("summary"):
            st.markdown("**Summary**")
            st.markdown(
                f"<div style='color:#D1D5DB;font-size:0.9rem;'>{selected['summary']}</div>",
                unsafe_allow_html=True,
            )

    st.divider()

    # ── Guardrailed report ────────────────────────────────────────────────────
    st.subheader("Guardrailed report")
    st.caption(
        "Every AI-drafted report passes enforce_report_guardrails() before it is "
        "shown: mandatory review banner, provenance line, and advice-phrase scrubbing."
    )

    with st.spinner("Building report…"):
        report = _rebuild_report(str(_DEFAULT_VCF))
        violations = enforce_report_guardrails(report)

    if violations:
        st.error("Guardrail violations detected:\n\n" + "\n".join(f"- {v}" for v in violations))
    else:
        st.success("Guardrails passed — no violations.")

    with st.expander("Full report", expanded=False):
        st.code(render_report(report), language="markdown")


@st.cache_data(show_spinner=False)
def _rebuild_report(vcf_path: str):
    """Rebuild the full report object from cached interpretations."""
    kb = _load_knowledge_base()
    variants = parse_vcf(vcf_path, max_variants=50, kb=kb)
    results = DeterministicInterpreter(kb=kb).run_batch(variants)
    return build_report(
        results,
        backend_used="deterministic",
        run_id="demo",
        vcf_path=vcf_path,
    )
