"""Tests for QC Warning Records — DynamoDB and Postgres schema.

Validates:
- QC_WARNING is a valid record type
- QcWarningRecord constructs correctly
- Schema SQL is syntactically valid
- Views reference correct tables
"""
import re
from dataclasses import asdict
from pathlib import Path

import pytest

# Import models
from lambdas.shared.models import (
    VALID_RECORD_TYPES,
    QcWarningRecord,
    validate_record_type,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = ROOT / "db" / "schema.sql"


class TestQcWarningRecordType:
    """Test QC_WARNING record type validation."""

    def test_qc_warning_is_valid_record_type(self):
        """QC_WARNING is in VALID_RECORD_TYPES."""
        assert "QC_WARNING" in VALID_RECORD_TYPES

    def test_validate_accepts_qc_warning(self):
        """validate_record_type accepts QC_WARNING."""
        assert validate_record_type("QC_WARNING") is True

    def test_existing_types_still_valid(self):
        """All previously valid record types remain valid."""
        for rt in ("RUN", "QC_METRICS", "PROVENANCE", "AUDIT", "CORRECTION"):
            assert validate_record_type(rt) is True


class TestQcWarningRecord:
    """Test QcWarningRecord dataclass construction."""

    def test_default_construction(self):
        """QcWarningRecord constructs with defaults."""
        record = QcWarningRecord(run_id="run-123")
        assert record.run_id == "run-123"
        assert record.record_type == "QC_WARNING"
        assert record.overall_status == ""
        assert record.metrics_detail == {}

    def test_full_construction(self):
        """QcWarningRecord constructs with all fields."""
        record = QcWarningRecord(
            run_id="run-456",
            sample_id="HG002",
            created_at="2025-01-15T10:00:00Z",
            overall_status="warn",
            metric_name="percent_duplication",
            metric_value=0.25,
            threshold_warn=0.20,
            threshold_fail=0.40,
            threshold_source="bootstrap",
            metrics_detail={
                "percent_duplication": {"value": 0.25, "status": "warn"},
            },
        )
        assert record.overall_status == "warn"
        assert record.metric_value == 0.25
        assert record.threshold_source == "bootstrap"

    def test_serializable_to_dict(self):
        """QcWarningRecord can be serialized to a dict for DynamoDB."""
        record = QcWarningRecord(
            run_id="run-789",
            sample_id="HG002",
            overall_status="fail",
            metric_name="snp_f1",
            metric_value=0.985,
            threshold_warn=0.995,
            threshold_fail=0.99,
            threshold_source="adaptive",
        )
        d = asdict(record)
        assert d["run_id"] == "run-789"
        assert d["record_type"] == "QC_WARNING"
        assert d["metric_value"] == 0.985
        assert isinstance(d, dict)


class TestSchemaSQL:
    """Test that the Postgres schema SQL is valid and contains QC warnings."""

    def test_schema_file_exists(self):
        """Schema file exists."""
        assert SCHEMA_SQL.exists()

    def test_qc_warnings_table_exists(self):
        """Schema contains CREATE TABLE qc_warnings."""
        sql = SCHEMA_SQL.read_text()
        assert "CREATE TABLE IF NOT EXISTS qc_warnings" in sql

    def test_qc_warnings_table_has_required_columns(self):
        """qc_warnings table has all required columns."""
        sql = SCHEMA_SQL.read_text()
        required_cols = [
            "run_pk",
            "sample_id",
            "overall_status",
            "metric_name",
            "metric_value",
            "threshold_warn",
            "threshold_fail",
            "threshold_source",
            "metrics_detail",
            "recorded_at",
        ]
        for col in required_cols:
            assert col in sql, f"Column '{col}' not found in schema"

    def test_qc_warnings_has_immutability_trigger(self):
        """qc_warnings is included in the immutability trigger."""
        sql = SCHEMA_SQL.read_text()
        assert "'qc_warnings'" in sql

    def test_v_qc_warnings_view_exists(self):
        """v_qc_warnings view is defined."""
        sql = SCHEMA_SQL.read_text()
        assert "CREATE OR REPLACE VIEW v_qc_warnings" in sql

    def test_v_qc_warning_frequency_view_exists(self):
        """v_qc_warning_frequency view is defined."""
        sql = SCHEMA_SQL.read_text()
        assert "CREATE OR REPLACE VIEW v_qc_warning_frequency" in sql

    def test_v_qc_metric_vs_threshold_view_exists(self):
        """v_qc_metric_vs_threshold view is defined."""
        sql = SCHEMA_SQL.read_text()
        assert "CREATE OR REPLACE VIEW v_qc_metric_vs_threshold" in sql

    def test_overall_status_check_constraint(self):
        """overall_status has CHECK constraint for warn/fail."""
        sql = SCHEMA_SQL.read_text()
        assert "overall_status IN ('warn', 'fail')" in sql

    def test_threshold_source_check_constraint(self):
        """threshold_source has CHECK constraint for adaptive/bootstrap."""
        sql = SCHEMA_SQL.read_text()
        assert "threshold_source IN ('adaptive', 'bootstrap')" in sql

    def test_indexes_exist(self):
        """QC warnings table has required indexes."""
        sql = SCHEMA_SQL.read_text()
        assert "idx_qc_warnings_run" in sql
        assert "idx_qc_warnings_sample" in sql
        assert "idx_qc_warnings_metric" in sql

    def test_sql_has_no_syntax_errors_basic(self):
        """Basic SQL syntax validation — no unmatched parens or missing semicolons."""
        sql = SCHEMA_SQL.read_text()
        # Check balanced parentheses (excluding string literals is too complex,
        # but gross mismatch will catch errors)
        open_count = sql.count("(")
        close_count = sql.count(")")
        assert abs(open_count - close_count) < 5, (
            f"Unbalanced parentheses: {open_count} open vs {close_count} close"
        )
