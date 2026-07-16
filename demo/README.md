# Interactive Demo — Data Explorer + Chatbot

A self-contained Streamlit app for exploring clinical genomics pipeline results
interactively. No database, no Docker, no API keys — just `pip install` and run.

## What's included

| Page | Description |
|------|-------------|
| **Data Explorer** | Interactive Plotly charts: SNP F1 trend, turnaround time, duplication rates, precision vs recall scatter, validation pass/fail breakdown. Filterable by sample, caller, and pipeline version. |
| **Chatbot** | Conversational interface to query pipeline data. Ask about summaries, failures, caller comparisons, or generate an AI-drafted report — all offline. |

## Quickstart

```bash
# From the repo root
pip install -r demo/requirements.txt
streamlit run demo/app.py
```

The app opens at `http://localhost:8501`. Use the sidebar to switch between pages.

## Data source

The demo loads data from two sources (no Postgres required):

1. **Embedded seed data** — 6 runs across 4 samples (HG002, HG003, HG004, NA12878),
   2 pipeline versions (0.2.0, 0.3.0), 2 callers (GATK, DeepVariant). Mirrors
   `db/seed_demo.sql`.
2. **Test fixtures** — any `*.metrics.json` files found under `tests/fixtures/` are
   loaded automatically.

## Chatbot capabilities

The chatbot answers questions about pipeline data using pattern matching and pandas
queries. No external LLM API is needed. Example prompts:

- "What's the overall summary?"
- "Which run had the best F1?"
- "Are there any failures?"
- "Compare GATK vs DeepVariant"
- "Show me details for HG002"
- "Compare pipeline versions"
- "Show the last 5 runs"
- "What are the duplication rates?"
- "Generate a report for HG002_chr20"

The report generation command reuses `ai-report/infer.py`'s offline renderer —
the same deterministic template that runs in CI.

## Dependencies

- `streamlit` — app framework and chat UI
- `plotly` — interactive charts
- `pandas` — data manipulation

All pinned in `requirements.txt`. Python 3.11+ recommended.

## Project structure

```
demo/
├── app.py              # Main entry point (streamlit run demo/app.py)
├── data_loader.py      # Data loading: seed + fixtures → DataFrame
├── pages/
│   ├── explorer.py     # Interactive visualization page
│   └── chat.py         # Chatbot page
├── requirements.txt    # Pinned dependencies
└── README.md           # This file
```
