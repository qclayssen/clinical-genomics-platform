"""DynamoDB-to-Postgres sync script for local development.

Reads DynamoDB single-table records and inserts them into the existing
normalized Postgres schema (samples, runs, qc_metrics, run_provenance,
audit_log). Designed for the Metabase dashboard bridge — keeps local
Postgres in sync with the DynamoDB metadata store.

Usage:
    # Standalone:
    python db/sync_dynamodb_to_postgres.py

    # As a module (e.g. from Lambda handler):
    from db.sync_dynamodb_to_postgres import sync_all

Environment variables:
    METADATA_TABLE  — DynamoDB table name (default: cgp-metadata)
    DATABASE_URL    — Postgres connection string
                     (default: postgresql://postgres:postgres@localhost:5432/cgp)

Requirements: 8.5, 8.6
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import boto3
import psycopg2
from psycopg2.extras import Json

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

METADATA_TABLE = os.environ.get("METADATA_TABLE", "cgp-metadata")
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cgp"
)

# Valid DynamoDB record types we process
_SYNCABLE_RECORD_TYPES = {"RUN", "QC_METRICS", "PROVENANCE", "AUDIT"}


# ── DynamoDB Reader ────────────────────────────────────────────────────────────


def scan_dynamodb(table_name: str | None = None) -> list[dict[str, Any]]:
    """Scan all items from the DynamoDB metadata table.

    Args:
        table_name: Override table name (defaults to METADATA_TABLE env var).

    Returns:
        List of raw DynamoDB item dicts.
    """
    table_name = table_name or METADATA_TABLE
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    items: list[dict[str, Any]] = []
    scan_kwargs: dict[str, Any] = {}

    while True:
        response = table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    return items


def group_by_run_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group DynamoDB items by run_id.

    Returns a dict mapping run_id to a dict of record_type -> item.
    For AUDIT records, stores them as a list under the 'AUDIT' key.
    """
    grouped: dict[str, dict[str, Any]] = defaultdict(dict)

    for item in items:
        run_id = item.get("run_id")
        record_type = item.get("record_type")

        if not run_id or not record_type:
            logger.warning("Skipping item with missing run_id or record_type: %s", item)
            continue

        if record_type not in _SYNCABLE_RECORD_TYPES:
            continue

        if record_type == "AUDIT":
            # Accumulate audit records as a list
            if "AUDIT" not in grouped[run_id]:
                grouped[run_id]["AUDIT"] = []
            grouped[run_id]["AUDIT"].append(item)
        else:
            grouped[run_id][record_type] = item

    return grouped


# ── Postgres Writer ────────────────────────────────────────────────────────────


def _parse_timestamp(ts_str: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp string to a datetime object.

    Returns None if the input is None or empty.
    """
    if not ts_str:
        return None
    try:
        # Handle both 'Z' suffix and '+00:00'
        ts_str = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        logger.warning("Could not parse timestamp: %s", ts_str)
        return None


def _ensure_sample(cur, sample_id: str, reference_build: str | None = None) -> None:
    """Ensure the sample exists in the samples table.

    Inserts if not present; does nothing on conflict (idempotent).
    """
    cur.execute(
        """
        INSERT INTO samples (sample_id, reference_build)
        VALUES (%s, %s)
        ON CONFLICT (sample_id) DO NOTHING
        """,
        (sample_id, reference_build or "GRCh38"),
    )


def _run_exists(cur, run_id: str) -> bool:
    """Check if a run_id already exists in the runs table."""
    cur.execute("SELECT 1 FROM runs WHERE run_id = %s", (run_id,))
    return cur.fetchone() is not None


def _get_run_pk(cur, run_id: str) -> int | None:
    """Get the auto-generated primary key for a run_id."""
    cur.execute("SELECT id FROM runs WHERE run_id = %s", (run_id,))
    row = cur.fetchone()
    return row[0] if row else None


def _insert_run(cur, run_id: str, run_record: dict[str, Any]) -> int | None:
    """Insert a run record into the runs table. Returns the auto-generated PK.

    Skips if run_id already exists (idempotent).
    """
    if _run_exists(cur, run_id):
        return _get_run_pk(cur, run_id)

    sample_id = run_record.get("sample_id", "")
    pipeline_version = run_record.get("pipeline_version", "0.0.0")
    git_commit = run_record.get("git_commit", "unknown")
    caller = run_record.get("caller", "HaplotypeCaller")
    started_at = _parse_timestamp(run_record.get("started_at"))
    exported_at = _parse_timestamp(run_record.get("exported_at"))
    validation_pass = bool(run_record.get("validation_pass", False))

    cur.execute(
        """
        INSERT INTO runs (run_id, sample_id, pipeline_version, git_commit, caller,
                          started_at, exported_at, validation_pass)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            run_id,
            sample_id,
            pipeline_version,
            git_commit,
            caller,
            started_at,
            exported_at,
            validation_pass,
        ),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _insert_qc_metrics(cur, run_pk: int, qc_record: dict[str, Any]) -> None:
    """Insert a qc_metrics record linked to the run PK."""
    cur.execute(
        """
        INSERT INTO qc_metrics (run_pk, percent_duplication, snp_precision,
                                snp_recall, snp_f1, n_variants)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            run_pk,
            float(qc_record.get("percent_duplication", 0.0)),
            float(qc_record.get("snp_precision", 0.0)),
            float(qc_record.get("snp_recall", 0.0)),
            float(qc_record.get("snp_f1", 0.0)),
            int(qc_record.get("n_variants", 0)),
        ),
    )


def _insert_provenance(cur, run_pk: int, prov_record: dict[str, Any]) -> None:
    """Insert a run_provenance record linked to the run PK."""
    input_checksums = prov_record.get("input_checksums", {})
    truth_version = prov_record.get("truth_set_version", "")

    cur.execute(
        """
        INSERT INTO run_provenance (run_pk, input_checksums, truth_version)
        VALUES (%s, %s, %s)
        """,
        (
            run_pk,
            Json(input_checksums),
            truth_version or None,
        ),
    )


def _insert_audit_records(
    cur, run_pk: int, audit_records: list[dict[str, Any]]
) -> int:
    """Insert audit_log records linked to the run PK.

    Returns the number of records inserted.
    """
    inserted = 0
    for audit in audit_records:
        action = audit.get("action", "")
        detail = audit.get("detail")
        actor = audit.get("actor", "lambda")
        occurred_at = _parse_timestamp(audit.get("created_at"))

        # Serialize detail if it's a dict
        detail_str = json.dumps(detail) if isinstance(detail, dict) else detail

        cur.execute(
            """
            INSERT INTO audit_log (run_pk, action, detail, actor, occurred_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                run_pk,
                action,
                detail_str,
                actor,
                occurred_at or datetime.now(timezone.utc),
            ),
        )
        inserted += 1

    return inserted


# ── Main Sync Logic ────────────────────────────────────────────────────────────


def sync_run(
    cur, run_id: str, records: dict[str, Any]
) -> dict[str, str]:
    """Sync a single run's records from DynamoDB to Postgres.

    Args:
        cur: Postgres cursor.
        run_id: The run identifier.
        records: Dict with keys RUN, QC_METRICS, PROVENANCE, AUDIT (list).

    Returns:
        Dict with status: 'synced' or 'skipped' and reason.
    """
    run_record = records.get("RUN")
    if not run_record:
        return {"status": "skipped", "reason": "no RUN record"}

    sample_id = run_record.get("sample_id", "")
    if not sample_id:
        return {"status": "skipped", "reason": "missing sample_id"}

    # Check if already synced (idempotent)
    if _run_exists(cur, run_id):
        return {"status": "skipped", "reason": "already exists"}

    # Ensure sample exists
    reference_build = run_record.get("reference_build", "GRCh38")
    _ensure_sample(cur, sample_id, reference_build)

    # Insert run record
    run_pk = _insert_run(cur, run_id, run_record)
    if run_pk is None:
        return {"status": "skipped", "reason": "insert failed"}

    # Insert QC metrics if present
    qc_record = records.get("QC_METRICS")
    if qc_record:
        _insert_qc_metrics(cur, run_pk, qc_record)

    # Insert provenance if present
    prov_record = records.get("PROVENANCE")
    if prov_record:
        _insert_provenance(cur, run_pk, prov_record)

    # Insert audit records if present
    audit_records = records.get("AUDIT", [])
    if audit_records:
        _insert_audit_records(cur, run_pk, audit_records)

    return {"status": "synced", "reason": "ok"}


def sync_all(
    items: list[dict[str, Any]] | None = None,
    database_url: str | None = None,
    table_name: str | None = None,
) -> dict[str, int]:
    """Sync all DynamoDB records to Postgres.

    Can be called with pre-fetched items (from Lambda) or will scan
    DynamoDB directly when items is None (standalone mode).

    Args:
        items: Pre-fetched DynamoDB items, or None to scan.
        database_url: Postgres connection string override.
        table_name: DynamoDB table name override.

    Returns:
        Summary dict with keys: synced, skipped, errors.
    """
    db_url = database_url or DATABASE_URL

    # Fetch from DynamoDB if items not provided
    if items is None:
        logger.info("Scanning DynamoDB table: %s", table_name or METADATA_TABLE)
        items = scan_dynamodb(table_name)
        logger.info("Fetched %d items from DynamoDB", len(items))

    # Group by run_id
    grouped = group_by_run_id(items)
    logger.info("Found %d unique run_ids to process", len(grouped))

    summary = {"synced": 0, "skipped": 0, "errors": 0}

    # Connect to Postgres and sync
    conn = psycopg2.connect(db_url)
    try:
        conn.autocommit = False
        cur = conn.cursor()

        for run_id, records in grouped.items():
            try:
                result = sync_run(cur, run_id, records)
                if result["status"] == "synced":
                    summary["synced"] += 1
                    logger.info("Synced run %s", run_id)
                else:
                    summary["skipped"] += 1
                    logger.debug(
                        "Skipped run %s: %s", run_id, result["reason"]
                    )
            except Exception as e:
                summary["errors"] += 1
                logger.error("Error syncing run %s: %s", run_id, e)
                conn.rollback()
                # Re-open transaction for remaining runs
                cur = conn.cursor()
                continue

        conn.commit()
    finally:
        conn.close()

    return summary


def sync_records(
    records: list[dict[str, Any]],
    database_url: str | None = None,
) -> dict[str, int]:
    """Sync a list of DynamoDB records to Postgres.

    Convenience function for use by Lambda handlers that already have
    the records in memory (no DynamoDB scan needed).

    Args:
        records: List of DynamoDB record dicts.
        database_url: Postgres connection string override.

    Returns:
        Summary dict with keys: synced, skipped, errors.
    """
    return sync_all(items=records, database_url=database_url)


# ── CLI Entry Point ────────────────────────────────────────────────────────────


def main() -> None:
    """Run the sync script as a standalone CLI tool."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("DynamoDB → Postgres sync starting")
    logger.info("  DynamoDB table: %s", METADATA_TABLE)
    logger.info("  Postgres URL:   %s", DATABASE_URL.split("@")[-1])  # hide creds

    try:
        summary = sync_all()
    except Exception as e:
        logger.error("Sync failed: %s", e)
        sys.exit(1)

    logger.info("Sync complete: %s", summary)
    logger.info(
        "  %d synced, %d skipped, %d errors",
        summary["synced"],
        summary["skipped"],
        summary["errors"],
    )

    if summary["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
