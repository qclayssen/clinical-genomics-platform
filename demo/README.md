# Interactive Demo — Data Explorer, Variant Interpretation + LLM Pipeline Assistant

A self-contained Streamlit app for exploring clinical genomics pipeline results
interactively. Features rich Plotly visualizations, a step-by-step view of the ACMG
interpretation agent, and an LLM-powered conversational assistant that understands
genomics context.

## What's included

| Page | Description |
|------|-------------|
| **Home** | Landing page — what the platform is and where to look first. |
| **Data Explorer** | 8 interactive Plotly charts: SNP F1 trend with regression zone, turnaround time, duplication rates, precision vs recall scatter, QC metrics heatmap, run timeline (Gantt), validation pass/fail breakdown, and caller performance radar. All filterable by sample, caller, and pipeline version. |
| **Variant Interpretation** | Surfaces the interpretation agent in `ai-report/agent/`: parses a VCF, classifies each variant against ACMG evidence codes, and replays the reasoning trace one tool call at a time. Ends with the guardrail check on the drafted report. |
| **Pipeline Assistant** | Conversational interface powered by a local LLM (via Ollama) that reasons about pipeline data. Falls back gracefully to pattern matching when Ollama is unavailable. Supports streaming responses, report generation, and arbitrary natural-language questions. |

## Quickstart

```bash
# From the repo root
pip install -r demo/requirements.txt
streamlit run demo/app.py
```

The app opens at `http://localhost:8501`. Use the sidebar to switch between pages.

## LLM-Powered Assistant (Optional)

The Pipeline Assistant page upgrades to full natural-language understanding when
Ollama is running locally. This enables arbitrary questions, follow-up reasoning,
and contextual awareness of the conversation history.

### Setup

```bash
# Install Ollama (macOS)
brew install ollama

# Or download from https://ollama.ai

# Start the Ollama server
ollama serve

# Pull a model (any of these work — mistral is recommended)
ollama pull mistral        # 7B, fast, good quality
ollama pull llama3         # 8B, excellent reasoning
ollama pull phi3           # 3.8B, lightweight alternative
```

### How it works

1. On page load, the assistant checks if Ollama is reachable at `localhost:11434`
2. If available, it selects the best model from a priority list (mistral > llama3 > etc.)
3. The full pipeline dataset is injected as a system prompt with clinical context
4. Responses are **streamed** token-by-token for a responsive experience
5. Conversation history (last 10 messages) is maintained for follow-up questions

### Without Ollama

The assistant still works — it uses regex-based intent matching to handle common
queries like summaries, comparisons, failure lists, and report generation. You'll
see an "Offline Mode" indicator in the UI.

The intent table lives in `demo/intents.py`, deliberately separate from the page so
it imports without Streamlit and can be tested directly. Every phrase offered as a
suggestion chip in the UI is covered by a test in `tests/test_demo_chat.py`, so a
suggestion can't silently stop matching.

## Data Explorer Charts

The explorer page includes 8 production-quality visualizations:

| Chart | Type | Purpose |
|-------|------|---------|
| SNP F1 Trend | Line | Accuracy over time with clinical threshold + regression zone |
| Turnaround Time | Bar | Processing speed per run, coloured by caller |
| Duplication Rate | Grouped bar | Library quality with alert threshold at 8% |
| Precision vs Recall | Scatter (bubble) | Trade-off landscape, bubble size = variant count |
| QC Metrics Heatmap | Heatmap | Correlation matrix across 5 key metrics |
| Run Timeline | Gantt | Start/end times showing scheduling and concurrency |
| Validation Status | Stacked bar | Pass/fail breakdown by pipeline version |
| Caller Radar | Radar/polar | Multi-dimensional caller comparison (normalised) |

All charts use a consistent clinical genomics colour palette (teal/cyan/coral/amber)
with a dark theme optimised for extended viewing.

## Variant Interpretation

This page is a window onto the interpretation agent in `ai-report/agent/` — the
reasoning is the interesting part, and a table of final classifications hides exactly
the work worth showing.

It reads `tests/fixtures/tiny_truth.vcf` (committed, PRNP variants on chr20), looks
each variant up in the SQLite knowledge base at `ai-report/agent/data/`, applies ACMG
evidence codes, and renders:

- **Summary counts** per classification (Pathogenic → Benign)
- **A reasoning trace** per variant — thought, tool call, observation, answer — with
  raw tool output available in an expander, and a "Replay step by step" button
- **The classification panel** — ACMG evidence chips coloured by direction (P vs B),
  confidence, and a plain-language summary
- **The guardrailed report** — the drafted report is passed through
  `enforce_report_guardrails()` and the pass/fail result is shown, matching the same
  human-review rule the rest of the platform enforces ([ADR-0008](../docs/adr/0008-guardrails-human-in-the-loop.md))

The **deterministic interpreter is the default, not a fallback** — no LLM, no network,
no setup, so the page behaves identically on a laptop and in a container. Ollama, when
present, is an upgrade rather than a requirement.

## Data source

The demo loads data from two sources (no Postgres required):

1. **Embedded seed data** — 6 runs across 4 samples (HG002, HG003, HG004, NA12878),
   2 pipeline versions (0.2.0, 0.3.0), 2 callers (GATK, DeepVariant). Mirrors
   `db/seed_demo.sql`.
2. **Test fixtures** — any `*.metrics.json` files found under `tests/fixtures/` are
   loaded automatically.

## Docker Compose (full stack with Metabase)

If you want the full stack — Streamlit demo, Metabase BI dashboard, and Postgres with
seeded pipeline data — you can run everything locally with Docker Compose:

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (v20+)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2+, included with Docker Desktop)

### Start the stack

```bash
# From the repo root
docker compose up -d
```

This starts three services:

| Service | URL | Description |
|---------|-----|-------------|
| **Streamlit demo** | http://localhost:8501 | Data Explorer + Pipeline Assistant |
| **Metabase** | http://localhost:3000 | Production BI dashboard over pipeline data |
| **Postgres** | `localhost:5432` | Database (user: `cgp`, password: `cgp`, db: `cgp`) |

On first boot, Postgres automatically runs `db/schema.sql` and `db/seed_demo.sql`
to create tables and load the 6-run demo dataset.

### Configure Metabase

On first visit to http://localhost:3000, Metabase walks you through setup. When it
asks to add a database:

| Field | Value |
|-------|-------|
| Database type | PostgreSQL |
| Host | `postgres` |
| Port | `5432` |
| Database name | `cgp` |
| Username | `cgp` |
| Password | `cgp` |

After connecting, the `v_run_summary` view is the best starting point for building
dashboard cards. See `dashboards/metabase/README.md` for the pre-defined SQL queries.

### Metabase vs Streamlit

Both tools visualize the same pipeline data — they serve different audiences:

| Aspect | Metabase | Streamlit Demo |
|--------|----------|----------------|
| **Audience** | Lab managers, ops teams | Developers, reviewers, demos |
| **Setup** | Docker Compose + DB config | `pip install` + run |
| **Data source** | Live Postgres | Embedded seed + fixtures |
| **LLM assistant** | No | Yes (with Ollama) |
| **Customisation** | Drag-and-drop, saved questions | Code-driven, version-controlled |
| **Best for** | Daily ops monitoring | Code review, presentations, offline use |

### Stop the stack

```bash
docker compose down        # Stop containers (preserves data)
docker compose down -v     # Stop and delete Postgres data volume
```

### Rebuild after code changes

```bash
docker compose up -d --build demo   # Rebuild only the Streamlit container
```

## Dependencies

- `streamlit` — app framework and chat UI
- `plotly` — interactive charts (line, bar, scatter, heatmap, timeline, radar)
- `pandas` — data manipulation
- `numpy` — numerical operations (heatmap correlation)
- `httpx` — HTTP client for Ollama API communication

All pinned in `requirements.txt`. Python 3.11+ recommended.

## Project structure

```
demo/
├── .streamlit/
│   └── config.toml         # Theme: dark navy + teal clinical palette
├── app.py                  # Main entry point (streamlit run demo/app.py)
├── data_loader.py          # Data loading: seed + fixtures → DataFrame
├── intents.py              # Offline intent patterns (no Streamlit import; tested directly)
├── pages/
│   ├── home.py             # Landing page
│   ├── explorer.py         # 8-chart interactive visualization page
│   ├── interpret.py        # Variant interpretation — ACMG trace + guardrail check
│   └── chat.py             # LLM-powered pipeline assistant
├── requirements.txt        # Pinned dependencies
└── README.md               # This file
```

## Tests

The demo's testable logic is covered by the repo-root `pytest` suite — no Streamlit
or Ollama needed:

```bash
pytest tests/test_demo_chat.py
```

`conftest.py` at the repo root puts the project on `sys.path`, so `demo.*` and
`lambdas.*` import in tests without any environment setup.
