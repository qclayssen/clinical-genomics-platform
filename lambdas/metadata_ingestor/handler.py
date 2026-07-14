"""Metadata Ingestor Lambda handler.

Writes RUN, QC_METRICS, PROVENANCE, and AUDIT records to DynamoDB,
then syncs to local Postgres for Metabase visibility. Returns
{ingested: true} to Step Functions on success.

Requirements: 5.2, 5.4, 5.5, 5.6, 5.9, 8.5, 11.2
"""

import json
import logging
import os
import subprocess

from lambdas.shared.dynamo import write_item
from lambdas.shared.models import validate_record_type
from lambdas.shared.timestamps import now_iso8601

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Default provenance field values
_PIPELINE_VERSION = os.environ.get("PIPELINE_VERSION", "0.3.0")
_REFERENCE_BUILD = "GRCh38"
_REFERENCE_VERSION = "hg38"
_TRUTH_SET_VERSION = "GIAB_v4.2.1_HG002_chr20"


def _log(level: str, message: str, **kwargs) -> None:
    """Emit structured JSON log entry to stdout."""
    entry = {
        "timestamp": now_iso8601(),
        "level": level,
        "function": "cgp-metadata-ingestor",
        "message": message,
        **kwargs,
    }
    print(json.dumps(entry), flush=True)


def _get_git_commit() -> str:
    """Return the current git commit SHA, or 'unknown' if not available."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return "unknown"


def _build_run_record(event: dict, created_at: str) -> dict:
    """Build a RUN record for DynamoDB.

    Contains run-level metadata: identifiers, pipeline version, caller,
    and validation outcome.
    """
    return {
        "run_id": event["run_id"],
        "record_type": "RUN",
        "sample_id": event.get("sample_id", ""),
        "pipeline_version": _PIPELINE_VERSION,
        "git_commit": _get_git_commit(),
        "caller": event.get("caller", "HaplotypeCaller"),
        "validation_pass": event.get("validation_pass", False),
        "created_at": created_at,
    }


def _build_qc_metrics_record(event: dict, created_at: str) -> dict:
    """Build a QC_METRICS record for DynamoDB.

    Contains quality control metrics from the QC and validation stages.
    """
    qc_metrics = event.get("qc_metrics", {})
    return {
        "run_id": event["run_id"],
        "record_type": "QC_METRICS",
        "sample_id": event.get("sample_id", ""),
        "percent_duplication": qc_metrics.get("percent_duplication", 0.0),
        "snp_precision": event.get("precision", 0.0),
        "snp_recall": event.get("recall", 0.0),
        "snp_f1": event.get("f1", 0.0),
        "n_variants": event.get("n_variants", 0),
        "created_at": created_at,
    }


def _build_provenance_record(event: dict, created_at: str) -> dict:
    """Build a PROVENANCE record for DynamoDB.

    Contains full provenance data: checksums, tool versions, reference info.
    """
    return {
        "run_id": event["run_id"],
        "record_type": "PROVENANCE",
        "sample_id": event.get("sample_id", ""),
        "input_checksums": event.get("input_checksums", {}),
        "pipeline_version": _PIPELINE_VERSION,
        "caller_tool": event.get("caller", "HaplotypeCaller"),
        "caller_version": event.get("caller_version", "4.5.0.0"),
        "reference_build": _REFERENCE_BUILD,
        "reference_version": _REFERENCE_VERSION,
        "truth_set_version": _TRUTH_SET_VERSION,
        "created_at": created_at,
    }


def _build_audit_record(event: dict, created_at: str) -> dict:
    """Build an AUDIT record for DynamoDB.

    Records the METADATA_INGESTED action in the audit trail.
    """
    return {
        "run_id": event["run_id"],
        "record_type": "AUDIT",
        "sample_id": event.get("sample_id", ""),
        "action": "METADATA_INGESTED",
        "created_at": created_at,
    }


def _sync_to_postgres(records: list[dict], run_id: str) -> None:
    """Sync records to local Postgres for Metabase visibility.

    This is non-blocking: failures are logged as warnings but do not
    prevent the Lambda from succeeding. In production this would call
    the db/sync_dynamodb_to_postgres.py utility or a dedicated RDS Proxy.

    For the demo, this logs that a sync would happen.
    """
    try:
        _log(
            "INFO",
            "Postgres sync: would write records to local Postgres for Metabase",
            run_id=run_id,
            record_count=len(records),
            record_types=[r["record_type"] for r in records],
        )
    except Exception as e:
        _log(
            "WARNING",
            "Postgres sync failed (non-blocking)",
            run_id=run_id,
            error=str(e),
        )


def handler(event: dict, context=None) -> dict:
    """Lambda entry point for metadata ingestion.

    Receives the accumulated Step Functions payload, builds RUN, QC_METRICS,
    PROVENANCE, and AUDIT records, writes them to DynamoDB (with built-in
    3-retry exponential backoff), syncs to Postgres, and returns success.

    Args:
        event: Step Functions payload with keys:
            - run_id (str)
            - sample_id (str)
            - input_checksums (dict)
            - qc_metrics (dict)
            - vcf_key (str)
            - caller (str)
            - n_variants (int)
            - precision (float)
            - recall (float)
            - f1 (float)
            - validation_pass (bool)
            - export_key (str)
        context: Lambda context (unused).

    Returns:
        Dict with ingested=True and run_id.

    Raises:
        ClientError: If DynamoDB writes fail after 3 retries (triggers
            Step Functions failure state and CloudWatch alarm).
    """
    run_id = event["run_id"]
    sample_id = event.get("sample_id", "")
    metadata_table = os.environ["METADATA_TABLE"]

    _log("INFO", "Starting metadata ingestion", run_id=run_id, sample_id=sample_id)

    # Generate a single timestamp for all records in this ingestion
    created_at = now_iso8601()

    # Build all four records
    records = [
        _build_run_record(event, created_at),
        _build_qc_metrics_record(event, created_at),
        _build_provenance_record(event, created_at),
        _build_audit_record(event, created_at),
    ]

    # Validate record types before writing
    for record in records:
        record_type = record["record_type"]
        if not validate_record_type(record_type):
            _log(
                "ERROR",
                f"Invalid record_type: {record_type}",
                run_id=run_id,
                record_type=record_type,
            )
            raise ValueError(
                f"Invalid record_type '{record_type}'. "
                f"Allowed: RUN, QC_METRICS, PROVENANCE, AUDIT, CORRECTION"
            )

    # Write each record to DynamoDB (write_item has 3-retry built in).
    # If retries are exhausted, the ClientError propagates up and
    # Step Functions transitions to the failure/catch state.
    for record in records:
        record_type = record["record_type"]
        _log(
            "INFO",
            f"Writing {record_type} record to DynamoDB",
            run_id=run_id,
            record_type=record_type,
            table=metadata_table,
        )
        write_item(metadata_table, record)
        _log(
            "INFO",
            f"Successfully wrote {record_type} record",
            run_id=run_id,
            record_type=record_type,
        )

    # Non-blocking sync to local Postgres for Metabase
    _sync_to_postgres(records, run_id)

    _log(
        "INFO",
        "Metadata ingestion complete",
        run_id=run_id,
        sample_id=sample_id,
        records_written=len(records),
    )

    return {"ingested": True, "run_id": run_id}
