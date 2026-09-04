# FastAPI + OpenAPI service — design

**Date:** 2026-09-04
**Status:** Approved (user directed implementation directly after design review)

## Purpose

Add a small, self-contained FastAPI service (`api/`) exposing the platform's
run/QC/provenance data as a documented REST API. This is a portfolio addition
demonstrating FastAPI + OpenAPI proficiency; it does not replace Metabase or
the Streamlit demo.

## Architecture

```
api/
  __init__.py
  main.py            # FastAPI app, OpenAPI metadata, router mounting, /healthz
  models.py          # Pydantic v2 schemas
  dependencies.py    # get_repository() — fixture vs Postgres, chosen via CGP_DB_URL
  repository.py      # Repository protocol, FixtureRepository, PostgresRepository
  data/
    demo_runs.json   # synthetic multi-run fixture data (runs, qc_metrics, provenance, qc_warnings)
  routers/
    runs.py          # all HTTP routes
  requirements.txt
  README.md
tests/test_api.py    # TestClient tests against the fixture backend
```

Default mode is **offline/fixture-backed**: `uvicorn api.main:app --reload`
works with zero external setup, reading `api/data/demo_runs.json` and an
in-memory review-decision store. Setting `CGP_DB_URL` swaps in
`PostgresRepository`, which reads the existing `runs` / `qc_metrics` /
`run_provenance` / `qc_warnings` / `review_decisions` tables — no schema
changes. Both repositories implement the same `Repository` protocol and
return the same Pydantic response models, so the swap is a pure dependency
substitution (`Depends(get_repository)`).

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness check |
| GET | `/runs` | List runs; filter by `sample_id`, `caller`, `validation_pass`; paginated (`limit`/`offset`) |
| GET | `/runs/{run_id}` | Run detail + inline QC summary |
| GET | `/runs/{run_id}/provenance` | Full provenance stamp (checksums, versions, truth set) |
| GET | `/runs/{run_id}/qc-warnings` | QC threshold breaches for that run |
| POST | `/runs/{run_id}/review-decisions` | Record a reviewer approve/reject sign-off (insert-only) |

Unknown `run_id` → 404 via `HTTPException`. Invalid POST body (e.g. a
`decision` outside `approved`/`rejected`) → 422 from Pydantic validation.
The POST returns 201.

## OpenAPI/FastAPI features demonstrated

- `FastAPI(title=..., description=..., version=..., contact=..., openapi_tags=...)`
  with the same scope-honesty line as the README (not an accredited clinical
  test) baked into the description, so it renders in `/docs`.
- `response_model` + `Field(..., examples=...)` on every schema for a
  populated Swagger UI (`/docs`) and ReDoc (`/redoc`).
- `APIRouter` with tags, `Depends()`-based repository injection, and
  `Query()`-validated pagination/filter parameters.
- One insert-only POST demonstrating request-body validation and a 201
  response.
- `tests/test_api.py` using `fastapi.testclient.TestClient` against the
  fixture backend: list/detail 200s, unknown-run 404, valid/invalid POST.

## Out of scope

- No authentication (documented as a known gap for a real deployment, not
  implemented here — this is a demo API).
- No changes to `db/schema.sql`.
- No new AWS/CDK deployment for the API (it's runnable locally only, like the
  Streamlit demo).

## Docs updates

- New `api/README.md` (how to run, where docs live).
- `CLAUDE.md`: repo map row, "How to run the runnable parts" entry (verified
  running, no external deps), ruff first-party package addition.
- `ruff.toml`: add `api` to `known-first-party`.
