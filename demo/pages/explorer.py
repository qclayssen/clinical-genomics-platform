"""Interactive Data Explorer page.

Plotly-powered visualizations of pipeline QC, validation, and operational metrics.
Charts mirror the Metabase dashboard but run locally with no infrastructure.
"""

from __future__ import annotations

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from demo.data_loader import load_all_data, get_summary_stats


def render() -> None:
    """Render the data explorer page."""
    st.header("Pipeline Data Explorer")
    st.caption(
        "Interactive view of QC, validation, and turnaround metrics across pipeline runs. "
        "Data is loaded from the embedded seed (mirrors `db/seed_demo.sql`)."
    )

    df = load_all_data()
    stats = get_summary_stats(df)

    # ── KPI cards ──────────────────────────────────────────────────────────────
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total Runs", stats["total_runs"])
    kpi2.metric("Validation Pass Rate", f"{stats['pass_rate_pct']}%")
    kpi3.metric("Mean SNP F1", f"{stats['mean_snp_f1']:.4f}")
    kpi4.metric("Mean Turnaround", f"{stats['mean_turnaround_min']} min")

    st.divider()

    # ── Filters ────────────────────────────────────────────────────────────────
    with st.expander("Filters", expanded=False):
        col_sample, col_caller, col_version = st.columns(3)
        with col_sample:
            selected_samples = st.multiselect(
                "Sample", options=stats["samples"], default=stats["samples"]
            )
        with col_caller:
            selected_callers = st.multiselect(
                "Caller", options=stats["callers"], default=stats["callers"]
            )
        with col_version:
            selected_versions = st.multiselect(
                "Pipeline Version",
                options=stats["versions"],
                default=stats["versions"],
            )

    mask = (
        df["sample_id"].isin(selected_samples)
        & df["caller"].isin(selected_callers)
        & df["pipeline_version"].isin(selected_versions)
    )
    filtered = df[mask].copy()

    if filtered.empty:
        st.warning("No data matches the current filters.")
        return

    # ── Chart 1: SNP F1 trend by pipeline version + caller ─────────────────────
    st.subheader("SNP F1 Trend")
    fig_f1 = px.line(
        filtered.sort_values("started_at"),
        x="started_at",
        y="snp_f1",
        color="caller",
        symbol="pipeline_version",
        markers=True,
        hover_data=["run_id", "sample_id", "pipeline_version"],
        labels={
            "started_at": "Run Date",
            "snp_f1": "SNP F1",
            "caller": "Caller",
            "pipeline_version": "Version",
        },
    )
    # Add acceptance threshold line
    fig_f1.add_hline(
        y=0.99,
        line_dash="dash",
        line_color="red",
        annotation_text="Acceptance: F1 >= 0.99",
        annotation_position="bottom right",
    )
    fig_f1.update_layout(yaxis_range=[0.985, 1.001], height=400)
    st.plotly_chart(fig_f1, use_container_width=True)

    # ── Chart 2: Turnaround time per run ───────────────────────────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Turnaround Time")
        fig_ta = px.bar(
            filtered.sort_values("started_at"),
            x="run_id",
            y="turnaround_min",
            color="caller",
            hover_data=["sample_id", "pipeline_version"],
            labels={
                "run_id": "Run",
                "turnaround_min": "Minutes",
                "caller": "Caller",
            },
        )
        fig_ta.update_layout(height=350, xaxis_tickangle=-30)
        st.plotly_chart(fig_ta, use_container_width=True)

    # ── Chart 3: Duplication rate distribution ─────────────────────────────────
    with col_right:
        st.subheader("Duplication Rate")
        fig_dup = px.bar(
            filtered.sort_values("percent_duplication", ascending=False),
            x="sample_id",
            y="percent_duplication",
            color="pipeline_version",
            barmode="group",
            hover_data=["run_id", "caller"],
            labels={
                "sample_id": "Sample",
                "percent_duplication": "Dup Rate",
                "pipeline_version": "Version",
            },
        )
        fig_dup.update_layout(
            height=350,
            yaxis_tickformat=".1%",
        )
        st.plotly_chart(fig_dup, use_container_width=True)

    # ── Chart 4: Precision vs Recall scatter ───────────────────────────────────
    st.subheader("Precision vs Recall")
    fig_pr = px.scatter(
        filtered,
        x="snp_recall",
        y="snp_precision",
        color="caller",
        symbol="pipeline_version",
        size="n_variants",
        hover_data=["run_id", "sample_id", "snp_f1"],
        labels={
            "snp_recall": "SNP Recall",
            "snp_precision": "SNP Precision",
            "caller": "Caller",
            "n_variants": "Variants",
        },
    )
    fig_pr.update_layout(
        height=400,
        xaxis_range=[0.988, 1.001],
        yaxis_range=[0.994, 1.001],
    )
    st.plotly_chart(fig_pr, use_container_width=True)

    # ── Chart 5: Validation pass/fail breakdown ────────────────────────────────
    st.subheader("Validation Status")
    pass_counts = (
        filtered.groupby(["pipeline_version", "validation_pass"])
        .size()
        .reset_index(name="count")
    )
    pass_counts["status"] = pass_counts["validation_pass"].map(
        {True: "PASS", False: "FAIL"}
    )
    fig_pass = px.bar(
        pass_counts,
        x="pipeline_version",
        y="count",
        color="status",
        barmode="stack",
        color_discrete_map={"PASS": "#2ecc71", "FAIL": "#e74c3c"},
        labels={
            "pipeline_version": "Pipeline Version",
            "count": "Runs",
            "status": "Status",
        },
    )
    fig_pass.update_layout(height=300)
    st.plotly_chart(fig_pass, use_container_width=True)

    # ── Raw data table ─────────────────────────────────────────────────────────
    with st.expander("Raw Data Table"):
        display_cols = [
            "run_id",
            "sample_id",
            "pipeline_version",
            "caller",
            "snp_f1",
            "snp_precision",
            "snp_recall",
            "percent_duplication",
            "n_variants",
            "turnaround_min",
            "validation_pass",
        ]
        st.dataframe(
            filtered[display_cols].style.format(
                {
                    "snp_f1": "{:.4f}",
                    "snp_precision": "{:.4f}",
                    "snp_recall": "{:.4f}",
                    "percent_duplication": "{:.3f}",
                    "turnaround_min": "{:.1f}",
                }
            ),
            use_container_width=True,
        )
