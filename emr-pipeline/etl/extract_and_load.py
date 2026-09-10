#!/usr/bin/env python3
"""Extract ICU admissions + ED consultations from the mock EMR and load them
into a local, insert-only warehouse.

This stands in for the "ODBC extraction from the EMR into a local warehouse"
step of an ICU/Virtual-ED research data pipeline. By default the extraction
connection is sqlite3 (stdlib) against `mock_emr/mock_emr.db`. Set the
EMR_ODBC_DSN environment variable to a real ODBC connection string and
`_connect()` below opens a genuine `pyodbc` connection instead — everything
downstream (pandas `.read_sql`, transforms, provenance stamping) is
driver-agnostic and untouched either way. See `emr-pipeline/README.md`.

Design mirrors this repo's genomics pipeline:
  - `pipeline/bin/build_metrics.py`  -> provenance stamp (git commit, checksums,
    row counts) written alongside every load, never overwritten.
  - `db/schema.sql`                  -> insert-only staging tables with
    UPDATE/DELETE-blocking triggers (see `emr-pipeline/sql/warehouse_schema.sql`).

Usage:
    python emr-pipeline/etl/extract_and_load.py
    python emr-pipeline/etl/extract_and_load.py --dry-run
    python emr-pipeline/etl/extract_and_load.py --source PATH --warehouse PATH
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_MODULE_DIR = _HERE.parent
DEFAULT_SOURCE_DB = _MODULE_DIR / "mock_emr" / "mock_emr.db"
DEFAULT_WAREHOUSE_DB = _MODULE_DIR / "warehouse.db"
SCHEMA_SQL = _MODULE_DIR / "sql" / "warehouse_schema.sql"

ODBC_DSN_ENV_VAR = "EMR_ODBC_DSN"


def _connect_odbc(dsn: str):
    """Open a real ODBC connection to an EMR reporting database via pyodbc.

    `pyodbc` is an optional dependency — it is only imported here, the
    instant a real DSN is actually requested, so the demo path (sqlite,
    no DSN set) never needs it installed. Example DSN shape (Microsoft's
    ODBC Driver 18 for SQL Server, see `emr-pipeline/README.md` for a
    docker-compose SQL Server target this has actually been run against):

        DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost,1433;
        DATABASE=EMR_RPT;UID=sa;PWD=...;Encrypt=yes;TrustServerCertificate=yes;

    A hospital EMR reporting database (Cerner/EPIC/iPM style) would use the
    same call with a different DRIVER/SERVER/DATABASE and real credentials —
    nothing else in this module changes, because `extract()` below only
    depends on the DB-API 2.0 `.cursor()`/`.close()` surface pyodbc and
    sqlite3 both implement.
    """
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError(
            f"{ODBC_DSN_ENV_VAR} is set but pyodbc is not installed — "
            f"pip install pyodbc (and the matching platform ODBC driver) "
            f"to use a real EMR connection."
        ) from exc
    return pyodbc.connect(dsn)


def _connect(source_db_path: Path):
    """Open the EMR data source.

    Returns a DB-API 2.0 connection: a real `pyodbc` connection when
    EMR_ODBC_DSN is set (see `_connect_odbc()`), otherwise the synthetic
    sqlite mock EMR used by this demo. `extract()` below calls
    `pandas.read_sql()` against whichever connection comes back, so nothing
    downstream (transforms, provenance stamping, insert-only load) needs to
    know or care which one it is.
    """
    odbc_dsn = os.environ.get(ODBC_DSN_ENV_VAR)
    if odbc_dsn:
        return _connect_odbc(odbc_dsn)
    if not source_db_path.exists():
        raise FileNotFoundError(
            f"mock EMR not found at {source_db_path} — run "
            f"emr-pipeline/mock_emr/build_mock_emr.py first, or set "
            f"{ODBC_DSN_ENV_VAR} to connect to a real EMR via ODBC instead"
        )
    return sqlite3.connect(source_db_path)


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=_MODULE_DIR,
            capture_output=True, text=True, timeout=5, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def extract(source_db_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Extract the two source tables as DataFrames."""
    conn = _connect(source_db_path)
    try:
        icu = pd.read_sql("SELECT * FROM icu_admissions", conn)
        ed = pd.read_sql("SELECT * FROM ed_consultations", conn)
    finally:
        conn.close()
    return icu, ed


def transform_icu_admissions(icu: pd.DataFrame) -> pd.DataFrame:
    """Add derived QC fields: length of stay, missing-field markers."""
    out = icu.copy()
    admit = pd.to_datetime(out["admit_datetime"])
    discharge = pd.to_datetime(out["discharge_datetime"])
    # Still-admitted rows (no discharge_datetime) get a null LOS, not a crash.
    out["length_of_stay_hours"] = (discharge - admit).dt.total_seconds() / 3600.0
    return out


def transform_ed_consultations(ed: pd.DataFrame) -> pd.DataFrame:
    out = ed.copy()
    out["note_char_length"] = out["consult_note"].str.len()
    return out


def missing_field_count(df: pd.DataFrame, required_cols: list[str]) -> int:
    """Count rows with at least one null in the given required columns."""
    return int(df[required_cols].isna().any(axis=1).sum())


def checksum_extract(icu: pd.DataFrame, ed: pd.DataFrame) -> str:
    """SHA-256 over a canonical serialization of both extracted frames."""
    h = hashlib.sha256()
    h.update(icu.sort_values("admission_id").to_csv(index=False).encode("utf-8"))
    h.update(ed.sort_values("consult_id").to_csv(index=False).encode("utf-8"))
    return h.hexdigest()


def ensure_warehouse(warehouse_db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(warehouse_db_path)
    conn.executescript(SCHEMA_SQL.read_text())
    return conn


def load(
    conn: sqlite3.Connection,
    icu: pd.DataFrame,
    ed: pd.DataFrame,
    batch_id: str,
    source_db_path: Path,
    dry_run: bool,
) -> dict:
    """Load the transformed extracts into the insert-only staging tables.

    Every row carries `extraction_batch_id` — a re-run never overwrites a
    previous batch's rows, matching the insert-only philosophy of
    db/schema.sql.
    """
    icu_missing = missing_field_count(
        icu, ["admit_datetime", "apache_ii_score", "discharge_datetime"]
    )
    checksum = checksum_extract(icu, ed)
    extracted_at = datetime.now(timezone.utc).isoformat()

    provenance = {
        "extraction_batch_id": batch_id,
        "source_db_path": str(source_db_path),
        "git_commit": _git_commit(),
        "extracted_at": extracted_at,
        "icu_admissions_rows": len(icu),
        "ed_consultations_rows": len(ed),
        "icu_admissions_missing_fields": icu_missing,
        "extract_checksum": checksum,
        "dry_run": int(dry_run),
    }

    if dry_run:
        return provenance

    icu_load = icu.copy()
    icu_load.insert(0, "extraction_batch_id", batch_id)
    icu_load[[
        "extraction_batch_id", "admission_id", "mrn", "age_years", "sex",
        "admit_datetime", "discharge_datetime", "unit", "admission_source",
        "primary_diagnosis", "diagnosis_icd10_am", "apache_ii_score",
        "ventilated", "vasopressor_support", "outcome", "length_of_stay_hours",
    ]].to_sql("staging_icu_admissions", conn, if_exists="append", index=False)

    ed_load = ed.copy()
    ed_load.insert(0, "extraction_batch_id", batch_id)
    ed_load[[
        "extraction_batch_id", "consult_id", "mrn", "consult_datetime",
        "referring_clinician", "consult_note", "note_char_length",
    ]].to_sql("staging_ed_consultations", conn, if_exists="append", index=False)

    conn.execute(
        """INSERT INTO etl_provenance (
            extraction_batch_id, source_db_path, git_commit, extracted_at,
            icu_admissions_rows, ed_consultations_rows,
            icu_admissions_missing_fields, extract_checksum, dry_run
        ) VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            batch_id, str(source_db_path), provenance["git_commit"], extracted_at,
            len(icu), len(ed), icu_missing, checksum, int(dry_run),
        ),
    )
    conn.commit()
    return provenance


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=str(DEFAULT_SOURCE_DB), help="mock EMR sqlite path")
    ap.add_argument("--warehouse", default=str(DEFAULT_WAREHOUSE_DB), help="warehouse sqlite path")
    ap.add_argument("--dry-run", action="store_true",
                     help="extract + transform + print provenance, but do not write to the warehouse")
    args = ap.parse_args()

    source_db_path = Path(args.source)
    warehouse_db_path = Path(args.warehouse)
    batch_id = f"batch-{uuid.uuid4().hex[:12]}"

    icu_raw, ed_raw = extract(source_db_path)
    icu = transform_icu_admissions(icu_raw)
    ed = transform_ed_consultations(ed_raw)

    conn = ensure_warehouse(warehouse_db_path) if not args.dry_run else None
    try:
        if args.dry_run:
            provenance = load(None, icu, ed, batch_id, source_db_path, dry_run=True)
        else:
            provenance = load(conn, icu, ed, batch_id, source_db_path, dry_run=False)
    finally:
        if conn is not None:
            conn.close()

    print(json.dumps(provenance, indent=2, sort_keys=True))
    if args.dry_run:
        print("[dry-run] no rows written to the warehouse", file=sys.stderr)
    else:
        print(f"loaded batch {batch_id} into {warehouse_db_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
