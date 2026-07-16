"""Clinical Genomics Platform — Interactive Demo

Multi-page Streamlit app with:
  1. Data Explorer — interactive Plotly charts of pipeline metrics
  2. Chatbot — conversational interface to query pipeline results

Run with:
    streamlit run demo/app.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Clinical Genomics Platform Demo",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar navigation ────────────────────────────────────────────────────────

st.sidebar.title("Clinical Genomics Platform")
st.sidebar.caption("Interactive demo — no infrastructure required")

page = st.sidebar.radio(
    "Navigate",
    options=["Data Explorer", "Chatbot"],
    index=0,
)

st.sidebar.divider()
st.sidebar.markdown(
    """
**About this demo**

Visualise pipeline QC, validation, and operational metrics
from the seed data (6 runs, 4 samples, 2 callers).

The chatbot lets you query the data conversationally —
no API keys or external services needed.

---

[Repository](https://github.com/quentinclayssen/clinical-genomics-platform)
| [Docs](https://github.com/quentinclayssen/clinical-genomics-platform/tree/main/docs)
"""
)

# ── Page routing ──────────────────────────────────────────────────────────────

if page == "Data Explorer":
    from demo.pages.explorer import render

    render()
elif page == "Chatbot":
    from demo.pages.chat import render

    render()
