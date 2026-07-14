"""Ingestion Trigger Lambda handler.

Parses S3 event input from Step Functions, validates FASTQ extensions,
generates a unique run_id, computes SHA-256 checksums of input files,
writes an INGESTION_STARTED audit record, and returns run metadata to
the state machine.

Event format (from EventBridge via Step Functions):
    {"detail": {"bucket": {"name": "..."}, "object": {"key": "...", "size": ...}}}
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone

import boto3

from lambdas.shared.audit import build_audit_record
from lambdas.shared.dynamo import write_item
from lambdas.shared.timestamps import now_iso8601


# Case-insensitive pattern for valid FASTQ extensions
_FASTQ_EXTENSION_RE = re.compile(r"\.(fastq|fq)\.gz$", re.IGNORECASE)


def _log(level: str, message: str, **kwargs) -> None:
    """Emit structured JSON log entry to stdout."""
    entry = {
        "timestamp": now_iso8601(),
        "level": level,
        "function": "cgp-ingestion-trigger",
        "message": message,
        **kwargs,
    }
    print(json.dumps(entry), flush=True)


def _validate_fastq_extension(key: str) -> bool:
    """Validate that an S3 key has a valid FASTQ extension (case-insensitive).

    Valid extensions: .fastq.gz, .fq.gz (any case).
    """
    return _FASTQ_EXTENSION_RE.search(key) is not None


def _extract_sample_id(key: str) -> str:
    """Extract sample_id from the S3 key.

    Strategy: take the filename, strip the extension parts and read pair suffix,
    then extract the base sample identifier (first underscore-delimited token).

    Examples:
        raw/HG002_chr20/HG002_chr20_R1.fastq.gz -> HG002
        raw/NA12878/NA12878_R2.fq.gz -> NA12878
    """
    # Get filename from the key
    filename = key.rsplit("/", 1)[-1]
    # Remove .fastq.gz or .fq.gz extension
    name = _FASTQ_EXTENSION_RE.sub("", filename)
    # Remove read pair suffix like _R1, _R2, _1, _2
    name = re.sub(r"[_](?:R[12]|[12])$", "", name)
    # Take the first underscore-delimited token as sample_id
    sample_id = name.split("_")[0]
    return sample_id


def _generate_run_id(sample_id: str, region: str) -> str:
    """Generate a unique run_id from timestamp, sample_id, and AWS region.

    Format: run_YYYYMMDD_<sample_id>_<region>_NNN
    where NNN is derived from the current time (HHMMSS) to provide uniqueness.
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")
    # Use HHMMSS as a sequence-like suffix for intra-day uniqueness
    seq = now.strftime("%H%M%S")
    return f"run_{date_str}_{sample_id}_{region}_{seq}"


def _compute_sha256(bucket: str, key: str) -> str:
    """Stream an S3 object and compute its SHA-256 checksum.

    Returns:
        Hex-encoded SHA-256 hash prefixed with 'sha256:'.
    """
    s3_client = boto3.client("s3")
    response = s3_client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]

    sha256_hash = hashlib.sha256()
    for chunk in body.iter_chunks(chunk_size=8192):
        sha256_hash.update(chunk)

    return f"sha256:{sha256_hash.hexdigest()}"


def handler(event: dict, context=None) -> dict:
    """Lambda entry point for ingestion trigger.

    Parses the S3 event, validates the FASTQ extension, generates a run_id,
    computes input file checksums, writes an INGESTION_STARTED audit record,
    and returns the run metadata to Step Functions.

    Args:
        event: EventBridge event payload forwarded by Step Functions.
            Format: {"detail": {"bucket": {"name": "..."}, "object": {"key": "...", "size": ...}}}
        context: Lambda context (unused).

    Returns:
        Dict with run_id, sample_id, and input_checksums.

    Raises:
        ValueError: If the S3 object does not have a valid FASTQ extension.
    """
    # Parse S3 event
    detail = event["detail"]
    bucket_name = detail["bucket"]["name"]
    object_key = detail["object"]["key"]
    object_size = detail["object"].get("size", 0)

    _log("INFO", "Ingestion trigger received", bucket=bucket_name, key=object_key, size=object_size)

    # Validate FASTQ extension
    if not _validate_fastq_extension(object_key):
        _log(
            "ERROR",
            "Invalid file extension — not a FASTQ file",
            bucket=bucket_name,
            key=object_key,
        )
        raise ValueError(
            f"Invalid file extension: '{object_key}' does not have a .fastq.gz or .fq.gz extension"
        )

    # Extract sample_id from the key
    sample_id = _extract_sample_id(object_key)

    # Generate run_id
    region = os.environ.get("AWS_REGION", "us-east-1")
    run_id = _generate_run_id(sample_id, region)

    _log("INFO", "Generated run_id", run_id=run_id, sample_id=sample_id, region=region)

    # Compute SHA-256 checksum of the input file
    _log("INFO", "Computing SHA-256 checksum", run_id=run_id, key=object_key)
    checksum = _compute_sha256(bucket_name, object_key)
    filename = object_key.rsplit("/", 1)[-1]
    input_checksums = {filename: checksum}

    _log("INFO", "Checksum computed", run_id=run_id, filename=filename, checksum=checksum)

    # Write INGESTION_STARTED audit record
    metadata_table = os.environ["METADATA_TABLE"]
    audit_record = build_audit_record(
        run_id=run_id,
        sample_id=sample_id,
        action="INGESTION_STARTED",
        detail={
            "bucket": bucket_name,
            "key": object_key,
            "size": object_size,
        },
    )

    _log("INFO", "Writing INGESTION_STARTED audit record", run_id=run_id)
    write_item(metadata_table, audit_record)

    _log("INFO", "Ingestion trigger complete", run_id=run_id, sample_id=sample_id)

    return {
        "run_id": run_id,
        "sample_id": sample_id,
        "input_checksums": input_checksums,
    }
