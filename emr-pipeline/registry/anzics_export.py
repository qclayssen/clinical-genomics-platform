#!/usr/bin/env python3
"""Map warehouse ICU admissions into a stub ANZICS APD-style export.

This is a **structural demo** of the field-mapping + validation pattern used
when routinely submitting to a registry like the ANZICS Adult Patient Database
(APD) — it is NOT a certified or complete ANZICS APD data dictionary
implementation. Field names and value sets here are a small, documented
*subset* chosen to show the pattern (required-field checks, range checks, a
validation report), not to be authoritative about the real APD spec. A real
submission would use ANZICS's actual data dictionary, its exact field set,
and its real submission mechanism/credentials — none of which this repo has
or claims to have.

Usage:
    python emr-pipeline/registry/anzics_export.py --warehouse emr-pipeline/warehouse.db
    python emr-pipeline/registry/anzics_export.py --warehouse ... --out-dir emr-pipeline/registry/out
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_MODULE_DIR = _HERE.parent
DEFAULT_WAREHOUSE_DB = _MODULE_DIR / "warehouse.db"
DEFAULT_OUT_DIR = _HERE / "out"

# Subset of ANZICS-APD-style fields used for this demo (documented subset,
# not the full data dictionary).
REQUIRED_FIELDS = [
    "patient_study_no", "unit", "admit_datetime", "age_years", "sex",
    "apache_ii_score", "primary_diagnosis_code", "outcome", "admission_source",
]

# (min, max) inclusive range checks for numeric fields.
RANGE_CHECKS = {
    "age_years": (0, 110),
    "apache_ii_score": (0, 71),          # the published APACHE II range
    "length_of_stay_hours": (0, 24 * 365),
}

VALID_OUTCOMES = {"discharged", "died", "transferred", "unknown"}

# ICU registries (ANZICS APD included) publicly document admission source as
# a core field because it drives elective-vs-emergency casemix reporting —
# ED / operating theatre / ward / inter-hospital retrieval are the commonly
# used categories. `elective_admission` is derived from it below rather than
# stored separately, matching how APD-style extracts commonly report it.
VALID_ADMISSION_SOURCES = {"ED", "Theatre", "Ward", "Retrieval", "unknown"}
ELECTIVE_ADMISSION_SOURCES = {"Theatre"}


def _pseudonymise_mrn(mrn: str) -> str:
    """Registry submissions use a study number, not the MRN. Demo: a stable
    hash stands in for a real re-identification-resistant study ID scheme."""
    return "STUDY-" + hashlib.sha256(mrn.encode("utf-8")).hexdigest()[:10].upper()


def load_latest_batch_icu_admissions(warehouse_db_path: Path) -> list[dict]:
    conn = sqlite3.connect(warehouse_db_path)
    conn.row_factory = sqlite3.Row
    try:
        latest_batch = conn.execute(
            "SELECT extraction_batch_id FROM etl_provenance "
            "WHERE dry_run = 0 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if latest_batch is None:
            return []
        batch_id = latest_batch["extraction_batch_id"]
        rows = conn.execute(
            "SELECT * FROM staging_icu_admissions WHERE extraction_batch_id = ?",
            (batch_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def map_to_apd_record(row: dict) -> dict:
    outcome = (row.get("outcome") or "unknown").strip() or "unknown"
    admission_source = (row.get("admission_source") or "unknown").strip() or "unknown"
    return {
        "patient_study_no": _pseudonymise_mrn(row["mrn"]),
        "unit": row.get("unit"),
        "admit_datetime": row.get("admit_datetime"),
        "discharge_datetime": row.get("discharge_datetime"),
        "age_years": row.get("age_years"),
        "sex": row.get("sex"),
        "apache_ii_score": row.get("apache_ii_score"),
        "primary_diagnosis_code": row.get("diagnosis_icd10_am"),
        "ventilated": bool(row.get("ventilated")),
        "vasopressor_support": bool(row.get("vasopressor_support")),
        "length_of_stay_hours": row.get("length_of_stay_hours"),
        "outcome": outcome if outcome in VALID_OUTCOMES else "unknown",
        "admission_source": admission_source if admission_source in VALID_ADMISSION_SOURCES else "unknown",
        "elective_admission": admission_source in ELECTIVE_ADMISSION_SOURCES,
        "_source_admission_id": row.get("admission_id"),  # kept for the validation report only
    }


def validate_record(record: dict) -> list[str]:
    """Return a list of validation error strings; empty list = valid."""
    errors = []
    for f in REQUIRED_FIELDS:
        if record.get(f) in (None, "", "unknown"):
            errors.append(f"missing required field: {f}")

    for field_name, (lo, hi) in RANGE_CHECKS.items():
        value = record.get(field_name)
        if value is None:
            continue
        if not (lo <= value <= hi):
            errors.append(f"{field_name}={value} out of expected range [{lo}, {hi}]")

    if record.get("outcome") not in VALID_OUTCOMES:
        errors.append(f"outcome={record.get('outcome')!r} not in {sorted(VALID_OUTCOMES)}")

    if record.get("admission_source") not in VALID_ADMISSION_SOURCES:
        errors.append(
            f"admission_source={record.get('admission_source')!r} "
            f"not in {sorted(VALID_ADMISSION_SOURCES)}"
        )

    return errors


def build_export(rows: list[dict]) -> tuple[list[dict], dict]:
    records = [map_to_apd_record(r) for r in rows]
    report_entries = []
    valid_count = 0
    for record in records:
        errors = validate_record(record)
        is_valid = len(errors) == 0
        if is_valid:
            valid_count += 1
        report_entries.append({
            "admission_id": record["_source_admission_id"],
            "patient_study_no": record["patient_study_no"],
            "valid": is_valid,
            "errors": errors,
        })
    validation_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_records": len(records),
        "valid_records": valid_count,
        "invalid_records": len(records) - valid_count,
        "entries": report_entries,
        "note": (
            "Structural demo of ANZICS-APD-style field mapping + validation. "
            "Not a certified ANZICS submission format."
        ),
    }
    return records, validation_report


def write_csv(records: list[dict], out_path: Path) -> None:
    fieldnames = [k for k in records[0].keys() if k != "_source_admission_id"] if records else []
    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow({k: v for k, v in r.items() if k != "_source_admission_id"})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--warehouse", default=str(DEFAULT_WAREHOUSE_DB), help="warehouse sqlite path")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="output directory")
    args = ap.parse_args()

    warehouse_db_path = Path(args.warehouse)
    if not warehouse_db_path.exists():
        print(f"warehouse not found at {warehouse_db_path} — run "
              f"emr-pipeline/etl/extract_and_load.py first", file=sys.stderr)
        return 1

    rows = load_latest_batch_icu_admissions(warehouse_db_path)
    if not rows:
        print("no loaded ICU admissions found in the warehouse (only dry-run batches?)",
              file=sys.stderr)
        return 1

    records, validation_report = build_export(rows)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(records, out_dir / "anzics_apd_export.csv")
    (out_dir / "anzics_apd_export.json").write_text(
        json.dumps([{k: v for k, v in r.items() if k != "_source_admission_id"} for r in records],
                   indent=2, sort_keys=True, default=str)
    )
    (out_dir / "validation_report.json").write_text(json.dumps(validation_report, indent=2))

    print(json.dumps({
        "total_records": validation_report["total_records"],
        "valid_records": validation_report["valid_records"],
        "invalid_records": validation_report["invalid_records"],
        "out_dir": str(out_dir),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
