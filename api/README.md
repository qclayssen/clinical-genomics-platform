# REST API

A small FastAPI service exposing pipeline run results, QC metrics, provenance
stamps, and QC warnings, with full OpenAPI documentation. This is a portfolio
addition demonstrating FastAPI/OpenAPI proficiency — it complements, and does
not replace, the [Metabase dashboards](../dashboards/metabase/) or the
[Streamlit demo](../demo/).

## Run it (no setup required)

```bash
pip install -r api/requirements.txt
uvicorn api.main:app --reload
```

Then open:

- <http://127.0.0.1:8000/docs> — interactive Swagger UI
- <http://127.0.0.1:8000/redoc> — ReDoc
- <http://127.0.0.1:8000/openapi.json> — raw OpenAPI 3 schema

By default the API serves the committed demo fixtures in
[`api/data/demo_runs.json`](data/demo_runs.json) — three synthetic runs
shaped like `tests/fixtures/HG002_chr20.metrics.json`, including a warn-level
and a fail-level QC warning, and an in-memory review-decision store.

## Point it at a live database instead

```bash
export CGP_DB_URL="postgresql://user:pass@localhost:5432/cgp"
uvicorn api.main:app --reload
```

With `CGP_DB_URL` set, the same routes read from the `runs`, `qc_metrics`,
`run_provenance`, `qc_warnings`, and `review_decisions` tables defined in
[`db/schema.sql`](../db/schema.sql). `review_decisions` inserts respect the
schema's insert-only trigger — there is no update/delete path.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness check |
| GET | `/runs` | List runs (filter by `sample_id`, `caller`, `validation_pass`; paginated) |
| GET | `/runs/{run_id}` | Run summary + latest QC metrics |
| GET | `/runs/{run_id}/provenance` | Full provenance stamp |
| GET | `/runs/{run_id}/qc-warnings` | QC threshold breaches for the run |
| POST | `/runs/{run_id}/review-decisions` | Record a reviewer approve/reject sign-off |

## Tests

```bash
pytest tests/test_api.py
```

Runs against the fixture backend only — no database needed.

## Known limitations

This is a demo API: it has no authentication and is not deployed. See
[CLAUDE.md](../CLAUDE.md) for the project's overall scope-honesty note — this
is a portfolio project, not an accredited clinical test.
