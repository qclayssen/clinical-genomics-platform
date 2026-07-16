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

## Docker Compose (local hosting with Metabase)

If you want the full stack — Streamlit demo, Metabase dashboard, and Postgres with
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
| **Streamlit demo** | http://localhost:8501 | Data Explorer + Chatbot |
| **Metabase** | http://localhost:3000 | BI dashboard over pipeline data |
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
dashboard cards.

### Stop the stack

```bash
docker compose down        # Stop containers (preserves data)
docker compose down -v     # Stop and delete Postgres data volume
```

### Rebuild after code changes

```bash
docker compose up -d --build demo   # Rebuild only the Streamlit container
```

## Deploy to AWS (free tier)

For a publicly accessible version, deploy on a single EC2 t2.micro instance
(free tier eligible for 12 months):

```bash
cd infra
cdk deploy CgpDemoHosting
```

This provisions an EC2 instance that clones the repo and runs the same
`docker compose up` stack. After deploy, CDK outputs the public IP:

- Streamlit → `http://<public-ip>:8501`
- Metabase → `http://<public-ip>:3000`

Estimated cost: **$0/month** within AWS free tier (t2.micro 750 hrs + 20 GB EBS).

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
