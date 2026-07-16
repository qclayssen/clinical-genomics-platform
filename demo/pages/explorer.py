"""Interactive Data Explorer page.

Plotly-powered visualizations of pipeline QC, validation, and operational metrics.
Charts mirror the Metabase dashboard but run locally with no infrastructure.

This page provides a comprehensive operational view of the clinical genomics
pipeline — the same data a lab director would review each morning to assess
throughput, quality trends, and flagged failures.
"""

from __future__ import annotations

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from demo.data_loader import get_summary_stats, load_all_data

# ── Colour palette (consistent with theme) ────────────────────────────────────
COLORS = {
    "teal": "#00BFA6",
    "cyan": "#00E5FF",
    "coral": "#FF6B6B",
    "amber": "#FFB74D",
    "purple": "#B388FF",
    "slate": "#90A4AE",
    "pass": "#00BFA6",
    "fail": "#FF6B6B",
}

CALLER_COLORS = {"gatk": "#00BFA6", "deepvariant": "#B388FF"}
VERSION_COLORS = {"0.2.0": "#FFB74D", "0.3.0": "#00E5FF"}


def render() -> None:
    """Render the data explorer page."""
    st.markdown(
        '<p class="hero-title" style="font-size:1.8rem;">Pipeline Data Explorer</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="hero-subtitle" style="font-size:0.95rem;">'
        "Interactive QC, validation, and throughput metrics across all pipeline runs. "
        "Charts mirror the production Metabase dashboard — rendered locally with Plotly."
        "</p>",
        unsafe_allow_html=True,
    )

    df = load_all_data()
    stats = get_summary_stats(df)

    # ── KPI cards with sparkline context ───────────────────────────────────────
    st.subheader("Key Performance Indicators")
    st.caption(
        "At-a-glance operational health. These metrics aggregate across all runs "
        "and update as new pipeline executions complete."
    )

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric(
        "Total Runs",
        stats["total_runs"],
        help="Number of completed pipeline executions in the dataset",
    )
    kpi2.metric(
        "Validation Pass Rate",
        f"{stats['pass_rate_pct']}%",
        delta=f"{'above' if stats['pass_rate_pct'] >= 90 else 'below'} 90% target",
        delta_color="normal" if stats['pass_rate_pct'] >= 90 else "inverse",
        help="Percentage of runs achieving SNP F1 >= 0.99 (clinical acceptance threshold)",
    )
    kpi3.metric(
        "Mean SNP F1",
        f"{stats['mean_snp_f1']:.4f}",
        delta="above 0.99" if stats['mean_snp_f1'] >= 0.99 else "below 0.99",
        delta_color="normal" if stats['mean_snp_f1'] >= 0.99 else "inverse",
        help="Harmonic mean of precision and recall — the single most important accuracy metric",
    )
    kpi4.metric(
        "Mean Turnaround",
        f"{stats['mean_turnaround_min']} min",
        help="Average elapsed time from run start to export completion",
    )

    st.divider()

    # ── Filters ────────────────────────────────────────────────────────────────
    st.markdown("##### Filters")
    st.caption(
        "Narrow the data to specific samples, callers, or pipeline versions. "
        "All charts below respond to these filters in real time."
    )
    with st.expander("Configure Filters", expanded=False):
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
    st.subheader("SNP F1 Accuracy Trend")
    st.markdown(
        """
        Tracks variant calling accuracy over time. Each point is a completed run,
        coloured by variant caller. The **red dashed line** marks the clinical
        acceptance threshold (F1 >= 0.99) — runs below this line fail validation
        and require investigation before results can be reported.

        *Hover over points for run-level detail. This chart answers: "Is our accuracy
        stable, improving, or degrading?"*
        """
    )
    fig_f1 = px.line(
        filtered.sort_values("started_at"),
        x="started_at",
        y="snp_f1",
        color="caller",
        symbol="pipeline_version",
        markers=True,
        hover_data=["run_id", "sample_id", "pipeline_version"],
        color_discrete_map=CALLER_COLORS,
        labels={
            "started_at": "Run Date",
            "snp_f1": "SNP F1",
            "caller": "Caller",
            "pipeline_version": "Version",
        },
    )
    # Acceptance threshold
    fig_f1.add_hline(
        y=0.99,
        line_dash="dash",
        line_color=COLORS["coral"],
        annotation_text="Clinical acceptance: F1 >= 0.99",
        annotation_position="bottom right",
        annotation_font_color=COLORS["coral"],
    )
    # Highlight regression zone
    fig_f1.add_hrect(
        y0=0.985, y1=0.99,
        fillcolor=COLORS["coral"], opacity=0.05,
        line_width=0,
        annotation_text="Regression zone",
        annotation_position="top left",
        annotation_font_size=10,
        annotation_font_color=COLORS["slate"],
    )
    fig_f1.update_layout(
        yaxis_range=[0.985, 1.001],
        height=420,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_f1, use_container_width=True)

    # ── Chart 2 & 3: Turnaround + Duplication side by side ─────────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Turnaround Time")
        st.markdown(
            """
            Elapsed minutes from pipeline start to final export. Shorter is better —
            clinical labs target **< 90 minutes** for WES chr20 analysis. Bars are
            coloured by variant caller to reveal systematic speed differences.
            """
        )
        fig_ta = px.bar(
            filtered.sort_values("started_at"),
            x="run_id",
            y="turnaround_min",
            color="caller",
            color_discrete_map=CALLER_COLORS,
            hover_data=["sample_id", "pipeline_version"],
            labels={
                "run_id": "Run",
                "turnaround_min": "Minutes",
                "caller": "Caller",
            },
        )
        fig_ta.update_layout(
            height=380,
            xaxis_tickangle=-30,
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_ta, use_container_width=True)

    with col_right:
        st.subheader("Duplication Rate")
        st.markdown(
            """
            Library duplication percentage per sample. High duplication (> 8%) suggests
            over-amplification or low library complexity — a red flag for downstream
            variant calling reliability. Grouped by pipeline version.
            """
        )
        fig_dup = px.bar(
            filtered.sort_values("percent_duplication", ascending=False),
            x="sample_id",
            y="percent_duplication",
            color="pipeline_version",
            color_discrete_map=VERSION_COLORS,
            barmode="group",
            hover_data=["run_id", "caller"],
            labels={
                "sample_id": "Sample",
                "percent_duplication": "Dup Rate",
                "pipeline_version": "Version",
            },
        )
        # High-dup threshold
        fig_dup.add_hline(
            y=0.08,
            line_dash="dot",
            line_color=COLORS["amber"],
            annotation_text="Alert: > 8%",
            annotation_position="top right",
            annotation_font_color=COLORS["amber"],
        )
        fig_dup.update_layout(
            height=380,
            yaxis_tickformat=".1%",
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_dup, use_container_width=True)

    # ── Chart 4: Precision vs Recall scatter ───────────────────────────────────
    st.subheader("Precision vs Recall Landscape")
    st.markdown(
        """
        The **precision-recall trade-off** is fundamental to variant calling. Points in
        the upper-right corner represent ideal performance (high precision AND high recall).
        Bubble size encodes the total number of variants called — larger bubbles mean more
        variants were evaluated, giving higher statistical confidence.

        *This visualization helps identify whether a caller sacrifices recall for precision
        (conservative) or vice versa (aggressive).*
        """
    )
    fig_pr = px.scatter(
        filtered,
        x="snp_recall",
        y="snp_precision",
        color="caller",
        symbol="pipeline_version",
        size="n_variants",
        color_discrete_map=CALLER_COLORS,
        hover_data=["run_id", "sample_id", "snp_f1"],
        labels={
            "snp_recall": "SNP Recall",
            "snp_precision": "SNP Precision",
            "caller": "Caller",
            "n_variants": "Variants",
        },
    )
    fig_pr.update_layout(
        height=420,
        xaxis_range=[0.988, 1.001],
        yaxis_range=[0.994, 1.001],
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_pr, use_container_width=True)

    # ── Chart 5: QC Metrics Heatmap ───────────────────────────────────────────
    st.subheader("QC Metrics Heatmap")
    st.markdown(
        """
        A correlation heatmap showing how key quality metrics relate to each other
        across all filtered runs. Strong correlations (bright teal) indicate metrics
        that move together — useful for understanding which QC dimensions are
        independent signals vs. redundant measurements.

        For example, a strong negative correlation between duplication rate and F1
        would confirm that library quality directly impacts calling accuracy.
        """
    )
    heatmap_cols = ["snp_f1", "snp_precision", "snp_recall", "percent_duplication", "turnaround_min"]
    heatmap_labels = ["SNP F1", "Precision", "Recall", "Dup Rate", "Turnaround"]
    corr_matrix = filtered[heatmap_cols].corr()

    fig_heat = go.Figure(data=go.Heatmap(
        z=corr_matrix.values,
        x=heatmap_labels,
        y=heatmap_labels,
        colorscale=[
            [0, COLORS["coral"]],
            [0.5, "#1A1F2E"],
            [1, COLORS["teal"]],
        ],
        zmin=-1,
        zmax=1,
        text=np.round(corr_matrix.values, 2),
        texttemplate="%{text}",
        textfont={"size": 12},
        hovertemplate="<b>%{x}</b> vs <b>%{y}</b><br>Correlation: %{z:.3f}<extra></extra>",
    ))
    fig_heat.update_layout(
        height=400,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    # ── Chart 6: Run Timeline (Gantt-style) ────────────────────────────────────
    st.subheader("Run Timeline")
    st.markdown(
        """
        A Gantt-style timeline showing when each pipeline run started and completed.
        This view helps identify **scheduling patterns**, resource contention, and
        throughput bottlenecks. Overlapping bars indicate concurrent runs —
        useful for capacity planning.

        *Color indicates the variant caller used. Longer bars mean longer processing time.*
        """
    )
    timeline_df = filtered.sort_values("started_at").copy()
    fig_timeline = px.timeline(
        timeline_df,
        x_start="started_at",
        x_end="exported_at",
        y="run_id",
        color="caller",
        color_discrete_map=CALLER_COLORS,
        hover_data=["sample_id", "pipeline_version", "turnaround_min"],
        labels={
            "run_id": "Run",
            "caller": "Caller",
            "started_at": "Start",
            "exported_at": "End",
        },
    )
    fig_timeline.update_layout(
        height=max(250, len(timeline_df) * 50),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis_title="",
    )
    st.plotly_chart(fig_timeline, use_container_width=True)

    # ── Chart 7: Validation pass/fail breakdown ────────────────────────────────
    st.subheader("Validation Status")
    st.markdown(
        """
        Stacked view of pass/fail outcomes by pipeline version. A healthy pipeline
        should show predominantly green (PASS). Any red (FAIL) segments indicate
        runs where the SNP F1 dropped below the 0.99 clinical threshold —
        these require root-cause analysis before patient results are released.
        """
    )
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
        color_discrete_map={"PASS": COLORS["pass"], "FAIL": COLORS["fail"]},
        labels={
            "pipeline_version": "Pipeline Version",
            "count": "Runs",
            "status": "Status",
        },
    )
    fig_pass.update_layout(
        height=320,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_pass, use_container_width=True)

    # ── Chart 8: Caller Performance Radar ──────────────────────────────────────
    st.subheader("Caller Performance Radar")
    st.markdown(
        """
        Multi-dimensional comparison of variant callers across five key metrics.
        A larger polygon indicates better overall performance. This radar chart
        normalises each metric to a 0–1 scale so different units (minutes, ratios,
        percentages) can be compared on the same axes.

        *Useful for deciding which caller to default to for production runs.*
        """
    )
    caller_agg = filtered.groupby("caller").agg(
        f1=("snp_f1", "mean"),
        precision=("snp_precision", "mean"),
        recall=("snp_recall", "mean"),
        speed=("turnaround_min", "mean"),
        low_dup=("percent_duplication", "mean"),
    ).reset_index()

    # Normalise: higher is better for all (invert speed and dup)
    if len(caller_agg) > 0:
        categories = ["F1 Score", "Precision", "Recall", "Speed (inv.)", "Low Duplication"]
        fig_radar = go.Figure()

        for _, row in caller_agg.iterrows():
            # Normalise to 0-1 relative to the data range
            max_speed = filtered["turnaround_min"].max()
            max_dup = filtered["percent_duplication"].max()
            values = [
                row["f1"],
                row["precision"],
                row["recall"],
                1 - (row["speed"] / max_speed) if max_speed > 0 else 0.5,
                1 - (row["low_dup"] / max_dup) if max_dup > 0 else 0.5,
            ]
            fig_radar.add_trace(go.Scatterpolar(
                r=values + [values[0]],  # close the polygon
                theta=categories + [categories[0]],
                fill="toself",
                name=row["caller"],
                line_color=CALLER_COLORS.get(row["caller"], COLORS["slate"]),
                opacity=0.7,
            ))

        fig_radar.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0.9, 1.0]),
                bgcolor="rgba(0,0,0,0)",
            ),
            height=420,
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=True,
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    # ── Raw data table ─────────────────────────────────────────────────────────
    st.subheader("Raw Data Table")
    st.markdown(
        """
        Full dataset in tabular form for detailed inspection. All columns are sortable
        and the table is searchable. Use this to drill into specific runs identified
        from the charts above.
        """
    )
    with st.expander("Show Raw Data", expanded=False):
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
            height=300,
        )

    # ── Footer ─────────────────────────────────────────────────────────────────
    st.divider()
    st.caption(
        "This dashboard mirrors the production Metabase instance (port 3000). "
        "Data source: embedded seed data (6 runs) + any test fixtures. "
        "Charts update in real time as new pipeline runs complete and ingest into Postgres."
    )
