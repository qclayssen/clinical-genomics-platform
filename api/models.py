"""Pydantic response/request schemas for the FastAPI service.

Field names mirror the tables in db/schema.sql and the shape of
tests/fixtures/HG002_chr20.metrics.json so the fixture- and Postgres-backed
repositories can return identical models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class QcMetrics(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "percent_duplication": 0.061,
            "snp_precision": 0.9985,
            "snp_recall": 0.9971,
            "snp_f1": 0.9978,
            "n_variants": 61234,
        }]
    })

    percent_duplication: float | None = Field(None, description="Fraction of reads marked as PCR/optical duplicates")
    snp_precision: float | None = None
    snp_recall: float | None = None
    snp_f1: float = Field(..., description="hap.py SNP F1 vs the GIAB truth set; acceptance threshold is 0.99")
    n_variants: int | None = None


class Provenance(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "pipeline_version": "0.3.0",
            "git_commit": "abc1234",
            "caller": "gatk",
            "reference_build": "GRCh38.p14",
            "truth_version": "GIAB-v4.2.1",
            "started_at": "2026-03-01T09:00:00Z",
            "exported_at": "2026-03-01T10:12:00Z",
            "input_checksums": {"HG002_chr20.markdup.metrics": "943f06a0..."},
        }]
    })

    pipeline_version: str
    git_commit: str
    caller: str
    reference_build: str | None = None
    truth_version: str | None = None
    started_at: datetime | None = None
    exported_at: datetime | None = None
    input_checksums: dict[str, str] = Field(default_factory=dict)


class Run(BaseModel):
    """Run summary — list and detail views."""

    run_id: str
    sample_id: str
    pipeline_version: str
    caller: str
    validation_pass: bool
    started_at: datetime | None = None
    exported_at: datetime | None = None
    qc: QcMetrics


class QcWarning(BaseModel):
    run_id: str
    sample_id: str
    overall_status: Literal["warn", "fail"]
    metric_name: str
    metric_value: float
    threshold_warn: float
    threshold_fail: float
    threshold_source: Literal["adaptive", "bootstrap"]
    recorded_at: datetime


class ReviewDecisionCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "variant_key": "chr20:1234567:A>G",
            "classification": "likely_pathogenic",
            "decision": "approved",
            "reviewer": "j.smith",
            "comment": "Confirmed against ClinVar submission SCV000123456.",
        }]
    })

    variant_key: str = Field(..., description='"chrom:pos:ref>alt"')
    classification: str
    decision: Literal["approved", "rejected"]
    reviewer: str
    comment: str = ""


class ReviewDecision(ReviewDecisionCreate):
    id: int
    run_id: str
    decided_at: datetime


class ErrorDetail(BaseModel):
    detail: str
