"""QC Orchestrator Lambda handler.

Reads FASTQ from S3, performs QC analysis (simulated for demo),
writes QC output metrics to S3, and returns QC metrics to Step Functions.

In production, this would invoke fastp/FastQC for actual quality analysis.
For this demo/portfolio platform, it generates representative metrics.
"""

import json
import os
import random
import sys

from lambdas.shared.s3_utils import write_json
from lambdas.shared.timestamps import now_iso8601


def _log(level: str, message: str, **kwargs) -> None:
    """Emit structured JSON log entry to stdout."""
    entry = {
        "timestamp": now_iso8601(),
        "level": level,
        "function": "cgp-qc-orchestrator",
        "message": message,
        **kwargs,
    }
    print(json.dumps(entry), flush=True)


def _simulate_qc_metrics(run_id: str, sample_id: str) -> dict:
    """Generate representative QC metrics.

    In production, this would parse fastp/FastQC output.
    For demo purposes, generates realistic values for HG002 chr20.
    """
    # Seed from run_id for reproducibility across invocations
    seed = hash(run_id) & 0xFFFFFFFF
    rng = random.Random(seed)

    return {
        "percent_duplication": round(rng.uniform(0.03, 0.08), 4),
        "total_reads": rng.randint(800_000, 2_000_000),
        "q30_rate": round(rng.uniform(0.88, 0.96), 4),
        "mean_read_length": rng.randint(145, 151),
    }


def handler(event: dict, context=None) -> dict:
    """Lambda entry point for QC orchestration.

    Receives Step Functions payload with run information, simulates
    QC analysis, writes metrics to S3, and returns results.

    Args:
        event: Step Functions payload containing:
            - run_id: Unique run identifier
            - sample_id: Sample identifier (e.g., HG002)
            - input_checksums: Dict of filename -> sha256 checksums
        context: Lambda context (unused).

    Returns:
        Dict with run_id, sample_id, and qc_metrics for the next state.
    """
    run_id = event["run_id"]
    sample_id = event["sample_id"]
    input_checksums = event.get("input_checksums", {})

    _log("INFO", "QC orchestration started", run_id=run_id, sample_id=sample_id)

    # Get bucket name from environment
    bucket = os.environ["DATA_LAKE_BUCKET"]

    # Simulate QC analysis (production: invoke fastp/FastQC here)
    _log("INFO", "Running QC analysis", run_id=run_id, sample_id=sample_id)
    qc_metrics = _simulate_qc_metrics(run_id, sample_id)

    # Build QC output document
    qc_output = {
        "run_id": run_id,
        "sample_id": sample_id,
        "qc_metrics": qc_metrics,
        "input_checksums": input_checksums,
        "created_at": now_iso8601(),
    }

    # Write QC metrics to S3
    qc_key = f"work/{run_id}/qc/qc_metrics.json"
    _log("INFO", "Writing QC metrics to S3", run_id=run_id, s3_key=qc_key)
    write_json(bucket, qc_key, qc_output)

    _log(
        "INFO",
        "QC orchestration complete",
        run_id=run_id,
        sample_id=sample_id,
        percent_duplication=qc_metrics["percent_duplication"],
        total_reads=qc_metrics["total_reads"],
    )

    return {
        "run_id": run_id,
        "sample_id": sample_id,
        "qc_metrics": qc_metrics,
    }
