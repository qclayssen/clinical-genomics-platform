"""Home / Documentation landing page.

Provides a polished overview of the Clinical Genomics Platform with:
- Hero section with project summary
- Architecture diagram
- Feature cards
- Tech stack overview
- Quickstart guide
"""

from __future__ import annotations

import streamlit as st


def render() -> None:
    """Render the home / documentation page."""

    # ── Hero Section ───────────────────────────────────────────────────────────
    st.markdown(
        '<p class="hero-title">Clinical Genomics Insight Platform</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="hero-subtitle">'
        "End-to-end germline variant-calling pipeline — from raw WGS reads to "
        "validated variants, structured provenance, ops dashboards, and AI-drafted reports."
        "</p>",
        unsafe_allow_html=True,
    )

    # Badges
    st.markdown(
        """
        <div style="margin-bottom: 2rem;">
            <span class="badge badge-purple">Nextflow DSL2</span>&nbsp;
            <span class="badge badge-green">ISO 15189 Patterns</span>&nbsp;
            <span class="badge badge-blue">AWS CDK</span>&nbsp;
            <span class="badge badge-purple">Python 3.11+</span>&nbsp;
            <span class="badge badge-green">DeepVariant + GATK</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Feature Cards ──────────────────────────────────────────────────────────
    st.markdown("### What This Platform Does")
    st.markdown("")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-icon">🔬</div>
                <h3>Variant Calling Pipeline</h3>
                <p>Nextflow DSL2 pipeline with GATK HaplotypeCaller and DeepVariant.
                Adaptive QC, BQSR, and truth-set benchmarking via hap.py against GIAB references.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-icon">📊</div>
                <h3>Validation & Provenance</h3>
                <p>Every run tracked with insert-only Postgres provenance.
                SNP F1 acceptance thresholds, audit trails, and Metabase dashboards
                for operational monitoring.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-icon">🤖</div>
                <h3>AI Report Drafting</h3>
                <p>QLoRA-tuned LLM generates clinician-review reports from structured metrics.
                Deterministic offline fallback for CI. Guardrails enforce safety disclaimers.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("")
    col4, col5, col6 = st.columns(3)

    with col4:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-icon">☁️</div>
                <h3>AWS Infrastructure</h3>
                <p>CDK-defined infrastructure with Batch compute, S3 storage,
                ECR containers, and free-tier demo hosting on EC2.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col5:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-icon">🔒</div>
                <h3>Security & Compliance</h3>
                <p>Bandit + safety scanning in CI, SBOM generation, dependency pinning,
                and architecture patterns aligned with clinical data handling.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col6:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-icon">🧪</div>
                <h3>Testing & QA</h3>
                <p>Property-based testing with Hypothesis, schema validation,
                coverage gating at 80%, and deterministic pipeline stubs for CI.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("")
    st.divider()

    # ── Architecture Diagram ───────────────────────────────────────────────────
    st.markdown("### Architecture Overview")
    st.markdown("")

    st.markdown(
        """
        <div class="arch-box">
<span class="highlight">FASTQ Reads</span>
   │
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│  <span class="highlight">Nextflow Pipeline</span> (DSL2)                                           │
│                                                                      │
│  ┌─────────┐   ┌─────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │ FastQC  │──▶│ BWA-MEM │──▶│ MarkDup/BQSR │──▶│ <span class="success">HaplotypeCaller</span>│  │
│  │ + QC    │   │ Align   │   │ Calibration  │   │ / DeepVariant│   │
│  └─────────┘   └─────────┘   └──────────────┘   └──────┬───────┘   │
│                                                          │           │
│                                              ┌───────────▼────────┐  │
│                                              │  <span class="warn">hap.py Benchmark</span>  │  │
│                                              │  vs GIAB Truth Set │  │
│                                              └───────────┬────────┘  │
└──────────────────────────────────────────────────────────┼───────────┘
                                                           │
                                               ┌───────────▼────────┐
                                               │  <span class="highlight">metrics.json</span>      │
                                               │  Structured Output │
                                               └───────────┬────────┘
                                                           │
                        ┌──────────────────────────────────┼──────────────────┐
                        │                                  │                  │
                        ▼                                  ▼                  ▼
             ┌──────────────────┐             ┌────────────────┐   ┌─────────────────┐
             │ <span class="highlight">Postgres</span>          │             │ <span class="success">Metabase</span>        │   │ <span class="warn">AI Report</span>       │
             │ Provenance Store │             │ Ops Dashboard  │   │ QLoRA LLM Draft │
             │ (insert-only)    │             │                │   │ + Guardrails    │
             └──────────────────┘             └────────────────┘   └─────────────────┘
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("")
    st.divider()

    # ── Tech Stack ─────────────────────────────────────────────────────────────
    st.markdown("### Tech Stack")
    st.markdown("")

    cols = st.columns(6)
    techs = [
        ("🧬", "Nextflow", "DSL2 Pipeline"),
        ("🐍", "Python", "3.11+"),
        ("☁️", "AWS CDK", "Infrastructure"),
        ("🐘", "PostgreSQL", "Provenance"),
        ("📊", "Metabase", "Dashboards"),
        ("🤗", "QLoRA", "LLM Fine-tune"),
    ]
    for col, (icon, name, desc) in zip(cols, techs):
        with col:
            st.markdown(
                f'<div class="tech-item">{icon}<br/><strong>{name}</strong><br/>'
                f'<span style="font-size:0.75rem;color:#6B7280">{desc}</span></div>',
                unsafe_allow_html=True,
            )

    st.markdown("")
    st.divider()

    # ── Quickstart ─────────────────────────────────────────────────────────────
    st.markdown("### Quickstart")
    st.markdown("")

    tab_local, tab_docker, tab_aws = st.tabs(
        ["Local (pip)", "Docker Compose", "AWS Deploy"]
    )

    with tab_local:
        st.code(
            """# From the repo root
pip install -r demo/requirements.txt
streamlit run demo/app.py

# Opens at http://localhost:8501""",
            language="bash",
        )
        st.info(
            "This is the lightest option — no database, no Docker. "
            "Uses embedded seed data (6 runs across 4 samples)."
        )

    with tab_docker:
        st.code(
            """# Full stack: Streamlit + Metabase + Postgres
docker compose up -d

# Services:
#   Streamlit  → http://localhost:8501
#   Metabase   → http://localhost:3000
#   Postgres   → localhost:5432 (user: cgp, pass: cgp)""",
            language="bash",
        )
        st.info(
            "Postgres auto-runs schema.sql and seed_demo.sql on first boot. "
            "Connect Metabase to the `v_run_summary` view for instant dashboards."
        )

    with tab_aws:
        st.code(
            """# Deploy on EC2 free tier (t2.micro)
cd infra
cdk deploy CgpDemoHosting

# CDK outputs the public IP:
#   Streamlit → http://<public-ip>:8501
#   Metabase  → http://<public-ip>:3000""",
            language="bash",
        )
        st.info(
            "Estimated cost: $0/month within AWS free tier "
            "(t2.micro 750 hrs + 20 GB EBS, 12-month eligible)."
        )

    st.markdown("")
    st.divider()

    # ── Demo data description ──────────────────────────────────────────────────
    st.markdown("### Demo Data")
    st.markdown("")

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown(
            """
            The demo includes **6 pipeline runs** with embedded seed data:

            | Sample | Caller | Version | F1 |
            |--------|--------|---------|----|
            | HG002_chr20 | GATK | 0.2.0 | 0.9973 |
            | HG003_chr20 | GATK | 0.2.0 | 0.9967 |
            | HG004_chr20 | GATK | 0.2.0 | 0.9931 |
            | HG002_chr20 | DeepVariant | 0.3.0 | 0.9992 |
            | NA12878_chr20 | DeepVariant | 0.3.0 | 0.9985 |
            | HG003_chr20 | DeepVariant | 0.3.0 | 0.9981 |
            """
        )

    with col_right:
        st.markdown(
            """
            **Data Sources:**

            1. **Embedded seed** — mirrors `db/seed_demo.sql`, hardcoded in
               `data_loader.py` for zero-dependency operation

            2. **Test fixtures** — any `*.metrics.json` files under
               `tests/fixtures/` are loaded automatically

            **Validation threshold:** SNP F1 >= 0.99 (PASS/FAIL)

            **No Postgres required** for this demo — all data is in-memory.
            """
        )

    st.markdown("")
    st.divider()

    # ── Navigation hint ────────────────────────────────────────────────────────
    st.markdown("### Explore the Demo")
    st.markdown("")

    col_nav1, col_nav2 = st.columns(2)

    with col_nav1:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-icon">📈</div>
                <h3>Data Explorer</h3>
                <p>Interactive Plotly visualizations of SNP F1 trends, turnaround times,
                duplication rates, precision/recall scatter, and validation pass/fail breakdowns.
                Filterable by sample, caller, and pipeline version.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_nav2:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-icon">💬</div>
                <h3>Chatbot</h3>
                <p>Conversational interface to query pipeline data. Ask about summaries,
                failures, caller comparisons, or generate AI-drafted reports. Fully offline
                — no API keys needed.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("")
    st.caption(
        "Use the sidebar to navigate between pages. "
        "Built by Quentin Clayssen — solo-designed, solo-built."
    )
