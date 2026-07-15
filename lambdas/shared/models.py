"""Data classes for DynamoDB record types.

Defines the single-table record schema for the Clinical Genomics Platform
metadata store. Valid record types: RUN, QC_METRICS, PROVENANCE, AUDIT, CORRECTION, QC_WARNING.
"""

from dataclasses import dataclass, field
from typing import Any


VALID_RECORD_TYPES = {"RUN", "QC_METRICS", "PROVENANCE", "AUDIT", "CORRECTION", "QC_WARNING"}


def validate_record_type(record_type: str) -> bool:
    """Return True if record_type is one of the allowed DynamoDB sort key values."""
    return record_type in VALID_RECORD_TYPES


@dataclass
class RunRecord:
    """Represents a pipeline run record in DynamoDB."""

    run_id: str
    record_type: str = "RUN"
    sample_id: str = ""
    created_at: str = ""
    pipeline_version: str = ""
    git_commit: str = ""
    caller: str = ""
    started_at: str = ""
    exported_at: str = ""
    validation_pass: bool = False


@dataclass
class QcMetricsRecord:
    """Represents QC metrics for a run."""

    run_id: str
    record_type: str = "QC_METRICS"
    sample_id: str = ""
    created_at: str = ""
    percent_duplication: float = 0.0
    snp_precision: float = 0.0
    snp_recall: float = 0.0
    snp_f1: float = 0.0
    n_variants: int = 0


@dataclass
class ProvenanceRecord:
    """Represents provenance metadata for a run."""

    run_id: str
    record_type: str = "PROVENANCE"
    sample_id: str = ""
    created_at: str = ""
    input_checksums: dict[str, str] = field(default_factory=dict)
    pipeline_version: str = ""
    caller_tool: str = ""
    caller_version: str = ""
    reference_build: str = ""
    reference_version: str = ""
    truth_set_version: str = ""


@dataclass
class AuditRecord:
    """Represents an audit trail entry."""

    run_id: str
    record_type: str = "AUDIT"
    sample_id: str = ""
    created_at: str = ""
    action: str = ""
    detail: dict[str, Any] | None = None
    execution_start: str = ""
    execution_end: str = ""


@dataclass
class CorrectionRecord:
    """Represents a correction to a previous record."""

    run_id: str
    record_type: str = "CORRECTION"
    sample_id: str = ""
    created_at: str = ""
    original_record_type: str = ""
    correction_reason: str = ""
    corrected_values: dict[str, Any] = field(default_factory=dict)


@dataclass
class QcWarningRecord:
    """Represents a QC warning/failure detected during threshold evaluation.

    Stored in DynamoDB when the QC evaluation process detects a metric
    breach (warn or fail level). Enables historical tracking for adaptive
    thresholds and quarantine logic.
    """

    run_id: str
    record_type: str = "QC_WARNING"
    sample_id: str = ""
    created_at: str = ""
    overall_status: str = ""  # "warn" or "fail"
    metric_name: str = ""  # which metric triggered
    metric_value: float = 0.0
    threshold_warn: float = 0.0
    threshold_fail: float = 0.0
    threshold_source: str = ""  # "adaptive" or "bootstrap"
    metrics_detail: dict[str, Any] = field(default_factory=dict)  # full evaluation results
