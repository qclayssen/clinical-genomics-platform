"""Export Handler Lambda.

Builds a provenance-stamped metrics.json and writes it to S3 under
results/<run_id>/. Returns the export key for downstream consumers.

Requirements: 1.4, 4.1, 11.1
"""

import json
import logging
import os
import subprocess

from lambdas.shared.s3_utils import write_json
from lambdas.shared.timestamps import now_iso8601

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Default values for provenance fields
_PIPELINE_VERSION = os.environ.get("PIPELINE_VERSION", "1.0.0")
_REFERENCE_BUILD = "GRCh38"
_REFERENCE_VERSION = "hg38"
_TRUTH_SET_VERSION = "GIAB_v4.2.1_HG002_chr20"


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


def _build_metrics(event: dict) -> dict:
    """Construct the full metrics.json payload with provenance stamp.

    Args:
        event: Step Functions payload containing accumulated run data.

    Returns:
        Dict conforming to the provenance stamp schema.
    """
    git_commit = _get_git_commit()

    # Extract caller version from event or use default
    caller = event.get("caller", "HaplotypeCaller")
    caller_version = event.get("caller_version", "4.5.0.0")

    metrics = {
        "provenance": {
            "git_commit": git_commit,
            "pipeline_version": _PIPELINE_VERSION,
            "caller": caller,
            "caller_version": caller_version,
            "reference_build": _REFERENCE_BUILD,
            "reference_version": _REFERENCE_VERSION,
            "truth_set_version": _TRUTH_SET_VERSION,
            "input_checksums": event.get("input_checksums", {}),
            "n_variants": event.get("n_variants", 0),
        },
        "validation": {
            "snp": {
                "precision": event.get("precision", 0.0),
                "recall": event.get("recall", 0.0),
                "f1": event.get("f1", 0.0),
            },
        },
        "validation_pass": event.get("validation_pass", False),
        "qc": event.get("qc_metrics", {}),
        "sample": event.get("sample_id", ""),
    }
    return metrics


def handler(event: dict, context) -> dict:
    """Lambda entry point.

    Receives the accumulated Step Functions payload, builds the provenance-
    stamped metrics.json, writes it to S3, and returns the export key.

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
        context: Lambda context (unused).

    Returns:
        Dict with run_id, sample_id, and export_key.
    """
    run_id = event["run_id"]
    sample_id = event.get("sample_id", "")
    bucket = os.environ["DATA_LAKE_BUCKET"]

    logger.info(
        json.dumps(
            {
                "level": "INFO",
                "run_id": run_id,
                "function": "export_handler",
                "message": "Building metrics.json with provenance stamp",
                "timestamp": now_iso8601(),
            }
        )
    )

    # Build provenance-stamped metrics
    metrics = _build_metrics(event)

    # Write metrics.json to S3
    export_key = f"results/{run_id}/metrics.json"
    write_json(bucket, export_key, metrics)

    logger.info(
        json.dumps(
            {
                "level": "INFO",
                "run_id": run_id,
                "function": "export_handler",
                "message": f"Exported metrics.json to s3://{bucket}/{export_key}",
                "timestamp": now_iso8601(),
            }
        )
    )

    # NOTE: metrics.parquet write is stubbed for the demo.
    # In production, this would use pyarrow or pandas to write a Parquet file.
    # For the demo we write a JSON-lines alternative as a lightweight substitute.
    jsonl_key = f"results/{run_id}/metrics.jsonl"
    jsonl_content = json.dumps(metrics).encode("utf-8")
    from lambdas.shared.s3_utils import write_bytes

    write_bytes(bucket, jsonl_key, jsonl_content, content_type="application/jsonl")

    logger.info(
        json.dumps(
            {
                "level": "INFO",
                "run_id": run_id,
                "function": "export_handler",
                "message": f"Exported metrics.jsonl (parquet stub) to s3://{bucket}/{jsonl_key}",
                "timestamp": now_iso8601(),
            }
        )
    )

    return {
        "run_id": run_id,
        "sample_id": sample_id,
        "export_key": export_key,
    }
