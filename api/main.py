"""Clinical Genomics Insight Platform — REST API.

Run locally with no setup:

    uvicorn api.main:app --reload

Then open http://127.0.0.1:8000/docs for interactive Swagger UI, or
http://127.0.0.1:8000/redoc for ReDoc. The raw OpenAPI schema is served at
/openapi.json.

Set CGP_DB_URL to switch from the committed demo fixtures to a live Postgres
instance (see db/schema.sql) — the routes and response shapes are identical.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.repository import RunNotFoundError
from api.routers import runs

DESCRIPTION = """
Read/write access to pipeline run results, QC metrics, provenance stamps,
and QC warnings for the Clinical Genomics Insight Platform — a portfolio
germline SNV variant-calling pipeline (GIAB HG002 / NA24385, GRCh38 chr20).

**This is a portfolio project, not an accredited clinical test.** No result
served by this API should be used for clinical decision-making.

By default this API serves the committed demo fixtures (no database or
external services required). Set `CGP_DB_URL` to point it at a live
Postgres instance instead.
"""

app = FastAPI(
    title="Clinical Genomics Insight Platform API",
    description=DESCRIPTION,
    version="0.1.0",
    contact={"name": "Quentin Clayssen", "email": "quentin.clayssen@gmail.com"},
    openapi_tags=[
        {"name": "runs", "description": "Pipeline run results, QC metrics, provenance, and reviewer sign-off"},
        {"name": "meta", "description": "Service health"},
    ],
)

app.include_router(runs.router)


@app.exception_handler(RunNotFoundError)
def handle_run_not_found(request: Request, exc: RunNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.get("/healthz", tags=["meta"], summary="Liveness check")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
