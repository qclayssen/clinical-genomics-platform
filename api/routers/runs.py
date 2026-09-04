from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from api.dependencies import get_repository
from api.models import ErrorDetail, Provenance, QcWarning, ReviewDecision, ReviewDecisionCreate, Run
from api.repository import Repository

router = APIRouter(prefix="/runs", tags=["runs"])

NOT_FOUND_RESPONSE = {404: {"model": ErrorDetail, "description": "Run not found"}}


@router.get("", response_model=list[Run], summary="List pipeline runs")
def list_runs(
    sample_id: str | None = Query(None, description="Filter to a single sample, e.g. HG002_chr20"),
    caller: str | None = Query(None, description="Filter by variant caller, e.g. gatk"),
    validation_pass: bool | None = Query(None, description="Filter by hap.py validation outcome"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    repository: Repository = Depends(get_repository),
) -> list[Run]:
    return repository.list_runs(sample_id, caller, validation_pass, limit, offset)


@router.get(
    "/{run_id}",
    response_model=Run,
    responses=NOT_FOUND_RESPONSE,
    summary="Get a run's summary and latest QC metrics",
)
def get_run(run_id: str, repository: Repository = Depends(get_repository)) -> Run:
    return repository.get_run(run_id)


@router.get(
    "/{run_id}/provenance",
    response_model=Provenance,
    responses=NOT_FOUND_RESPONSE,
    summary="Get a run's full provenance stamp",
)
def get_provenance(run_id: str, repository: Repository = Depends(get_repository)) -> Provenance:
    return repository.get_provenance(run_id)


@router.get(
    "/{run_id}/qc-warnings",
    response_model=list[QcWarning],
    responses=NOT_FOUND_RESPONSE,
    summary="List QC threshold breaches for a run",
)
def list_qc_warnings(run_id: str, repository: Repository = Depends(get_repository)) -> list[QcWarning]:
    return repository.list_qc_warnings(run_id)


@router.post(
    "/{run_id}/review-decisions",
    response_model=ReviewDecision,
    status_code=status.HTTP_201_CREATED,
    responses=NOT_FOUND_RESPONSE,
    summary="Record a reviewer's sign-off on an AI-drafted variant classification",
)
def create_review_decision(
    run_id: str, decision: ReviewDecisionCreate, repository: Repository = Depends(get_repository)
) -> ReviewDecision:
    return repository.create_review_decision(run_id, decision)
