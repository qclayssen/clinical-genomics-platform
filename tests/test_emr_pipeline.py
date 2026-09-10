"""Tests for emr-pipeline/ — the ICU/Virtual-ED (VVED) data-engineering demo.

Runs under plain `pytest`, no external services: the mock EMR is a temp SQLite
file, the LLM structuring test uses `--offline` (no API key), and the ANZICS
export reads from a temp warehouse. Mirrors this repo's dependency-free test
style (see tests/test_build_metrics.py).
"""
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EMR_DIR = ROOT / "emr-pipeline"


def _load(module_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, module_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


build_mock_emr = _load(EMR_DIR / "mock_emr" / "build_mock_emr.py", "build_mock_emr")
extract_and_load = _load(EMR_DIR / "etl" / "extract_and_load.py", "extract_and_load")
structure_consult_notes = _load(EMR_DIR / "llm" / "structure_consult_notes.py", "structure_consult_notes")
anzics_export = _load(EMR_DIR / "registry" / "anzics_export.py", "anzics_export")


# ═══ mock EMR ═══════════════════════════════════════════════════════════════


def test_build_mock_emr_creates_expected_tables_and_row_counts(tmp_path):
    db_path = tmp_path / "mock_emr.db"
    build_mock_emr.build(db_path)

    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    try:
        icu_count = conn.execute("SELECT COUNT(*) FROM icu_admissions").fetchone()[0]
        ed_count = conn.execute("SELECT COUNT(*) FROM ed_consultations").fetchone()[0]
    finally:
        conn.close()

    assert 15 <= icu_count <= 20
    assert 15 <= ed_count <= 20


def test_mock_emr_data_is_clearly_synthetic(tmp_path):
    db_path = tmp_path / "mock_emr.db"
    build_mock_emr.build(db_path)
    conn = sqlite3.connect(db_path)
    try:
        mrns = [r[0] for r in conn.execute("SELECT mrn FROM icu_admissions").fetchall()]
        names = [r[0] for r in conn.execute("SELECT patient_name FROM icu_admissions").fetchall()]
    finally:
        conn.close()

    assert all(mrn.startswith("MOCK-") for mrn in mrns)
    assert all("TESTPATIENT" in name for name in names)


# ═══ ETL: extract + transform + insert-only load ═══════════════════════════


def _build_and_extract(tmp_path):
    source_db = tmp_path / "mock_emr.db"
    build_mock_emr.build(source_db)
    icu_raw, ed_raw = extract_and_load.extract(source_db)
    return source_db, icu_raw, ed_raw


def test_transform_icu_admissions_computes_length_of_stay(tmp_path):
    _, icu_raw, _ = _build_and_extract(tmp_path)
    icu = extract_and_load.transform_icu_admissions(icu_raw)

    assert "length_of_stay_hours" in icu.columns
    # ADM-0001: admit 2026-01-03T02:14, discharge 2026-01-07T11:00 -> 104.77h
    row = icu[icu["admission_id"] == "ADM-0001"].iloc[0]
    assert 104 < row["length_of_stay_hours"] < 105

    # ADM-0018 is still admitted (no discharge_datetime) -> null LOS, not a crash
    still_admitted = icu[icu["admission_id"] == "ADM-0018"].iloc[0]
    assert still_admitted["length_of_stay_hours"] != still_admitted["length_of_stay_hours"]  # NaN


def test_missing_field_count_flags_incomplete_row(tmp_path):
    _, icu_raw, _ = _build_and_extract(tmp_path)
    icu = extract_and_load.transform_icu_admissions(icu_raw)
    missing = extract_and_load.missing_field_count(
        icu, ["admit_datetime", "apache_ii_score", "discharge_datetime"]
    )
    assert missing >= 1  # ADM-0018 is deliberately incomplete


def test_dry_run_produces_provenance_without_writing(tmp_path):
    source_db, icu_raw, ed_raw = _build_and_extract(tmp_path)
    icu = extract_and_load.transform_icu_admissions(icu_raw)
    ed = extract_and_load.transform_ed_consultations(ed_raw)

    provenance = extract_and_load.load(
        None, icu, ed, "batch-test-dryrun", source_db, dry_run=True
    )

    assert provenance["dry_run"] == 1
    assert provenance["icu_admissions_rows"] == len(icu)
    assert provenance["ed_consultations_rows"] == len(ed)
    assert len(provenance["extract_checksum"]) == 64  # sha256 hex digest
    assert "git_commit" in provenance
    assert "extracted_at" in provenance


def test_checksum_is_stable_for_the_same_extract(tmp_path):
    _, icu_raw, ed_raw = _build_and_extract(tmp_path)
    icu = extract_and_load.transform_icu_admissions(icu_raw)
    ed = extract_and_load.transform_ed_consultations(ed_raw)
    assert extract_and_load.checksum_extract(icu, ed) == extract_and_load.checksum_extract(icu, ed)


def test_extract_via_real_odbc_matches_direct_sqlite_extract(tmp_path, monkeypatch):
    """Proves _connect()'s pyodbc branch is real, not just a comment.

    Skipped (not failed) when pyodbc or an ODBC driver manager isn't on this
    machine — see emr-pipeline/README.md for the one-time `brew install
    unixodbc sqliteodbc && pip install pyodbc` setup used to verify this.
    When available, this drives the *same* extract() function through a
    genuine pyodbc/ODBC connection and checks the result is byte-identical
    (via checksum_extract) to the direct sqlite3 path used by the rest of
    the suite.
    """
    pyodbc = pytest.importorskip("pyodbc")
    if "SQLite3" not in pyodbc.drivers():
        pytest.skip("no SQLite3 ODBC driver registered (see emr-pipeline/README.md)")

    source_db, icu_direct, ed_direct = _build_and_extract(tmp_path)

    monkeypatch.setenv(
        extract_and_load.ODBC_DSN_ENV_VAR, f"DRIVER=SQLite3;DATABASE={source_db}"
    )
    icu_odbc, ed_odbc = extract_and_load.extract(source_db)

    direct_checksum = extract_and_load.checksum_extract(
        extract_and_load.transform_icu_admissions(icu_direct),
        extract_and_load.transform_ed_consultations(ed_direct),
    )
    odbc_checksum = extract_and_load.checksum_extract(
        extract_and_load.transform_icu_admissions(icu_odbc),
        extract_and_load.transform_ed_consultations(ed_odbc),
    )
    assert odbc_checksum == direct_checksum


def test_load_is_insert_only_and_writes_provenance_row(tmp_path):
    source_db, icu_raw, ed_raw = _build_and_extract(tmp_path)
    icu = extract_and_load.transform_icu_admissions(icu_raw)
    ed = extract_and_load.transform_ed_consultations(ed_raw)

    warehouse_db = tmp_path / "warehouse.db"
    conn = extract_and_load.ensure_warehouse(warehouse_db)
    try:
        extract_and_load.load(conn, icu, ed, "batch-1", source_db, dry_run=False)
        extract_and_load.load(conn, icu, ed, "batch-2", source_db, dry_run=False)

        batches = conn.execute(
            "SELECT DISTINCT extraction_batch_id FROM staging_icu_admissions"
        ).fetchall()
        assert {b[0] for b in batches} == {"batch-1", "batch-2"}

        prov_rows = conn.execute("SELECT COUNT(*) FROM etl_provenance").fetchone()[0]
        assert prov_rows == 2

        # Insert-only: an UPDATE against a staging table must be rejected.
        import pytest as _pytest
        with _pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE staging_icu_admissions SET mrn = 'HACKED' WHERE extraction_batch_id = 'batch-1'"
            )
        with _pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM etl_provenance WHERE extraction_batch_id = 'batch-1'")
    finally:
        conn.close()


# ═══ LLM consult-note structuring (offline mode) ═══════════════════════════


def test_offline_extraction_has_guardrail_banner_and_provenance():
    note = ("64M p/w fever, hypotension BP 82/50, HR 118. Likely urosepsis. "
            "Started on IV fluids + broad spectrum abx. Discussed with ICU reg, "
            "for admission. High acuity.")
    result = structure_consult_notes.structure_note(
        "CON-TEST", note, offline=True, backend_name="deterministic"
    )
    d = result.to_dict()

    assert d["banner"] == structure_consult_notes.BANNER
    assert d["requires_clinician_validation"] is True
    assert d["provenance"]["backend"] == "offline-rule-based"
    assert len(d["provenance"]["source_note_sha256"]) == 64
    assert d["disposition"] in structure_consult_notes.VALID_DISPOSITIONS
    assert d["acuity_flag"] in structure_consult_notes.VALID_ACUITY
    assert d["diagnosis_code_guess"] == "A41.9"  # "urosepsis" keyword match
    assert d["disposition"] == "admit_icu"
    assert d["acuity_flag"] == "high"


def test_offline_extraction_defaults_to_unknown_for_uninformative_note():
    result = structure_consult_notes.structure_note(
        "CON-TEST-2", "Patient seen, notes pending.", offline=True, backend_name="deterministic"
    )
    d = result.to_dict()
    assert d["diagnosis_code_guess"] == "unknown"
    assert d["disposition"] == "unknown"


def test_guardrails_scrub_advice_phrasing_even_if_injected():
    fields = {
        "presenting_complaint": "chest pain",
        "disposition": "admit_icu",
        "acuity_flag": "high",
        "diagnosis_code_guess": "we recommend urgent cath lab",
    }
    result = structure_consult_notes.enforce_extraction_guardrails(
        fields, "CON-TEST-3", "chest pain, admit ICU", "fake-backend", "fake-model"
    )
    d = result.to_dict()
    assert "we recommend" not in d["diagnosis_code_guess"].lower()
    assert d["banner"] == structure_consult_notes.BANNER
    assert d["requires_clinician_validation"] is True


def test_structure_note_invalid_dispositon_falls_back_to_unknown():
    fields = {
        "presenting_complaint": "chest pain",
        "disposition": "not_a_real_value",
        "acuity_flag": "not_a_real_value",
        "diagnosis_code_guess": "I21.9",
    }
    result = structure_consult_notes.enforce_extraction_guardrails(
        fields, "CON-TEST-4", "note text", "fake-backend", "fake-model"
    )
    d = result.to_dict()
    assert d["disposition"] == "unknown"
    assert d["acuity_flag"] == "unknown"


# ═══ ANZICS registry export ═════════════════════════════════════════════════


def test_validate_record_flags_missing_required_field():
    record = {
        "patient_study_no": "STUDY-ABC1234567",
        "unit": "ICU",
        "admit_datetime": "2026-01-03T02:14:00",
        "age_years": 64,
        "sex": "M",
        "apache_ii_score": None,  # missing -> must fail validation
        "primary_diagnosis_code": "A41.9",
        "outcome": "discharged",
    }
    errors = anzics_export.validate_record(record)
    assert any("apache_ii_score" in e for e in errors)


def test_validate_record_flags_out_of_range_apache_score():
    record = {
        "patient_study_no": "STUDY-ABC1234567",
        "unit": "ICU",
        "admit_datetime": "2026-01-24T11:11:00",
        "age_years": 61,
        "sex": "M",
        "apache_ii_score": 90,  # out of the published 0-71 range
        "primary_diagnosis_code": "A41.9",
        "outcome": "discharged",
    }
    errors = anzics_export.validate_record(record)
    assert any("apache_ii_score" in e and "out of expected range" in e for e in errors)


def test_validate_record_passes_for_a_complete_record():
    record = {
        "patient_study_no": "STUDY-ABC1234567",
        "unit": "ICU",
        "admit_datetime": "2026-01-05T14:40:00",
        "age_years": 71,
        "sex": "F",
        "apache_ii_score": 15,
        "primary_diagnosis_code": "Z98.8",
        "outcome": "discharged",
        "length_of_stay_hours": 18.8,
        "admission_source": "ED",
    }
    assert anzics_export.validate_record(record) == []


def test_build_export_end_to_end_flags_the_incomplete_admission(tmp_path):
    source_db, icu_raw, ed_raw = _build_and_extract(tmp_path)
    icu = extract_and_load.transform_icu_admissions(icu_raw)
    ed = extract_and_load.transform_ed_consultations(ed_raw)
    warehouse_db = tmp_path / "warehouse.db"
    conn = extract_and_load.ensure_warehouse(warehouse_db)
    try:
        extract_and_load.load(conn, icu, ed, "batch-1", source_db, dry_run=False)
    finally:
        conn.close()

    rows = anzics_export.load_latest_batch_icu_admissions(warehouse_db)
    records, report = anzics_export.build_export(rows)

    assert report["total_records"] == len(rows)
    assert report["invalid_records"] >= 1  # ADM-0018 (incomplete) and/or ADM-0011 (out-of-range)

    invalid_ids = {e["admission_id"] for e in report["entries"] if not e["valid"]}
    assert "ADM-0018" in invalid_ids
    assert "ADM-0011" in invalid_ids
    assert "not a certified" in report["note"].lower() or "structural demo" in report["note"].lower()
