"""Audit record construction functions.

Builds structured audit trail records for the DynamoDB metadata store.
All records include a `created_at` timestamp in ISO 8601 UTC format.
"""

from .timestamps import now_iso8601


def build_completion_record(
    run_id: str,
    sample_id: str,
    execution_start: str,
    execution_end: str,
) -> dict:
    """Build a WORKFLOW_COMPLETE audit record.

    Args:
        run_id: Unique identifier for the pipeline run.
        sample_id: Sample identifier (e.g., HG002).
        execution_start: ISO 8601 timestamp of workflow start.
        execution_end: ISO 8601 timestamp of workflow end.

    Returns:
        Dict ready for DynamoDB PutItem.
    """
    return {
        "run_id": run_id,
        "record_type": "AUDIT",
        "sample_id": sample_id,
        "action": "WORKFLOW_COMPLETE",
        "execution_start": execution_start,
        "execution_end": execution_end,
        "created_at": now_iso8601(),
    }


def build_failure_record(
    run_id: str,
    sample_id: str,
    failed_state: str,
    error_cause: str,
) -> dict:
    """Build a WORKFLOW_FAILED audit record.

    Args:
        run_id: Unique identifier for the pipeline run.
        sample_id: Sample identifier (e.g., HG002).
        failed_state: Name of the state machine state that failed.
        error_cause: Description of the error cause.

    Returns:
        Dict ready for DynamoDB PutItem.
    """
    return {
        "run_id": run_id,
        "record_type": "AUDIT",
        "sample_id": sample_id,
        "action": "WORKFLOW_FAILED",
        "failed_state": failed_state,
        "error_cause": error_cause,
        "created_at": now_iso8601(),
    }


def build_audit_record(
    run_id: str,
    sample_id: str,
    action: str,
    detail: dict | None = None,
) -> dict:
    """Build a generic audit trail record.

    Args:
        run_id: Unique identifier for the pipeline run.
        sample_id: Sample identifier (e.g., HG002).
        action: Audit action type (e.g., INGESTION_STARTED, REPORT_DRAFTED).
        detail: Optional dict with additional action-specific data.

    Returns:
        Dict ready for DynamoDB PutItem.
    """
    record = {
        "run_id": run_id,
        "record_type": "AUDIT",
        "sample_id": sample_id,
        "action": action,
        "created_at": now_iso8601(),
    }
    if detail is not None:
        record["detail"] = detail
    return record
