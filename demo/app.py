"""Clinical Genomics Platform — Interactive Demo

Multi-page Streamlit app with:
  1. Home — Project overview, architecture, and quickstart
  2. Data Explorer — Interactive Plotly charts of pipeline metrics
  3. Pipeline Assistant — LLM-powered conversational interface to query results

Run with:
    streamlit run demo/app.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Clinical Genomics Platform",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS for polished aesthetics ─────────────────────────────────────────

st.markdown(
    """
    <style>
    /* Global tweaks */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0E1117 0%, #151B28 100%);
    }
    [data-testid="stSidebar"] .stMarkdown h1 {
        font-size: 1.3rem;
        letter-spacing: -0.02em;
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: #1A1F2E;
        border: 1px solid #2D3348;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    }
    [data-testid="stMetric"] label {
        color: #9CA3AF;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 1.8rem;
        font-weight: 700;
        color: #FAFAFA;
    }

    /* Expander styling */
    .streamlit-expanderHeader {
        font-weight: 600;
        color: #D1D5DB;
    }

    /* Chat messages */
    [data-testid="stChatMessage"] {
        border-radius: 12px;
        border: 1px solid #2D3348;
    }

    /* Divider */
    hr {
        border-color: #2D3348;
    }

    /* Hero section */
    .hero-title {
        font-size: 2.4rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        background: linear-gradient(135deg, #6C63FF 0%, #A78BFA 50%, #60A5FA 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 0.5rem;
    }
    .hero-subtitle {
        font-size: 1.1rem;
        color: #9CA3AF;
        margin-bottom: 2rem;
    }

    /* Feature cards */
    .feature-card {
        background: #1A1F2E;
        border: 1px solid #2D3348;
        border-radius: 12px;
        padding: 1.5rem;
        height: 100%;
        transition: border-color 0.2s ease;
    }
    .feature-card:hover {
        border-color: #6C63FF;
    }
    .feature-card h3 {
        margin-top: 0.5rem;
        font-size: 1.1rem;
        color: #FAFAFA;
    }
    .feature-card p {
        color: #9CA3AF;
        font-size: 0.9rem;
        line-height: 1.5;
    }
    .feature-icon {
        font-size: 2rem;
    }

    /* Architecture diagram box */
    .arch-box {
        background: #1A1F2E;
        border: 1px solid #2D3348;
        border-radius: 12px;
        padding: 1.5rem;
        font-family: 'JetBrains Mono', 'Fira Code', monospace;
        font-size: 0.82rem;
        line-height: 1.6;
        overflow-x: auto;
        color: #D1D5DB;
    }
    .arch-box .highlight {
        color: #6C63FF;
        font-weight: 600;
    }
    .arch-box .success {
        color: #34D399;
    }
    .arch-box .warn {
        color: #FBBF24;
    }

    /* Badge styling */
    .badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.03em;
    }
    .badge-purple {
        background: rgba(108, 99, 255, 0.15);
        color: #A78BFA;
        border: 1px solid rgba(108, 99, 255, 0.3);
    }
    .badge-green {
        background: rgba(52, 211, 153, 0.15);
        color: #34D399;
        border: 1px solid rgba(52, 211, 153, 0.3);
    }
    .badge-blue {
        background: rgba(96, 165, 250, 0.15);
        color: #60A5FA;
        border: 1px solid rgba(96, 165, 250, 0.3);
    }

    /* Tech stack grid */
    .tech-item {
        background: #1A1F2E;
        border: 1px solid #2D3348;
        border-radius: 8px;
        padding: 0.8rem 1rem;
        text-align: center;
        font-size: 0.85rem;
        color: #D1D5DB;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar navigation ────────────────────────────────────────────────────────

st.sidebar.markdown("# 🧬 CGP Demo")
st.sidebar.caption("Clinical Genomics Platform")

st.sidebar.divider()

page = st.sidebar.radio(
    "Navigation",
    options=["Home", "Data Explorer", "Pipeline Assistant"],
    index=0,
    label_visibility="collapsed",
)

st.sidebar.divider()

st.sidebar.markdown(
    """
<div style="font-size: 0.82rem; color: #6B7280; line-height: 1.6;">

**Demo Data**
6 runs · 4 samples · 2 callers
No infrastructure required

**LLM Mode**
Start Ollama for natural language:
`ollama serve && ollama pull mistral`

---

[GitHub](https://github.com/qclayssen/clinical-genomics-platform) ·
[Docs](https://github.com/qclayssen/clinical-genomics-platform/tree/main/docs) ·
[For Recruiters](https://github.com/qclayssen/clinical-genomics-platform/blob/main/docs/FOR-RECRUITERS.md)

</div>
""",
    unsafe_allow_html=True,
)

# ── Page routing ──────────────────────────────────────────────────────────────

if page == "Home":
    from demo.pages.home import render

    render()
elif page == "Data Explorer":
    from demo.pages.explorer import render

    render()
elif page == "Pipeline Assistant":
    from demo.pages.chat import render

    render()
