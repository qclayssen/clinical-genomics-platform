"""Unit tests for Lambda shared utilities.

Tests timestamps.py, dynamo.py, models.py, and audit.py with edge cases
and mocked dependencies.

Requirements: 5.2, 5.4, 5.9
"""

import re
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest
from botocore.exceptions import ClientError

from lambdas.shared.timestamps import format_iso8601, now_iso8601
from lambdas.shared.dynamo import write_item
from lambdas.shared.models import VALID_RECORD_TYPES, validate_record_type
from lambdas.shared.audit import (
    build_completion_record,
    build_failure_record,
    build_audit_record,
)


# ─── ISO 8601 pattern for validation ───
ISO8601_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


# ═══════════════════════════════════════════════════════════════════════════════
# timestamps.py tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestFormatISO8601:
    """Tests for format_iso8601() function."""

    def test_format_iso8601_basic(self):
        """Format a known datetime produces the expected ISO 8601 string."""
        dt = datetime(2024, 3, 15, 14, 30, 45, tzinfo=timezone.utc)
        result = format_iso8601(dt)
        assert result == "2024-03-15T14:30:45Z"

    def test_format_iso8601_truncates_microseconds(self):
        """Input with microseconds produces output with no microseconds."""
        dt = datetime(2024, 1, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)
        result = format_iso8601(dt)
        assert result == "2024-01-01T12:00:00Z"
        # Ensure no sub-second precision in output
        assert "." not in result

    def test_format_iso8601_naive_datetime(self):
        """Naive datetime (no tzinfo) is treated as UTC."""
        dt = datetime(2024, 6, 15, 8, 45, 30)
        result = format_iso8601(dt)
        assert result == "2024-06-15T08:45:30Z"

    def test_format_iso8601_timezone_aware(self):
        """Non-UTC timezone-aware datetime is converted to UTC."""
        # Create a datetime at UTC+5 (e.g., 14:00 in UTC+5 = 09:00 UTC)
        tz_plus5 = timezone(timedelta(hours=5))
        dt = datetime(2024, 7, 20, 14, 0, 0, tzinfo=tz_plus5)
        result = format_iso8601(dt)
        assert result == "2024-07-20T09:00:00Z"


class TestNowISO8601:
    """Tests for now_iso8601() function."""

    def test_now_iso8601_format(self):
        """now_iso8601() returns a string matching YYYY-MM-DDTHH:MM:SSZ pattern."""
        result = now_iso8601()
        assert ISO8601_PATTERN.match(result), (
            f"now_iso8601() returned {result!r} which does not match ISO 8601 pattern"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# dynamo.py tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteItem:
    """Tests for write_item() retry logic."""

    @patch("lambdas.shared.dynamo.boto3")
    def test_write_item_success(self, mock_boto3):
        """DynamoDB PutItem succeeds on first try."""
        mock_table = MagicMock()
        mock_table.put_item.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = write_item("test-table", {"run_id": "run-001", "record_type": "RUN"})

        assert result == {"ResponseMetadata": {"HTTPStatusCode": 200}}
        mock_table.put_item.assert_called_once_with(
            Item={"run_id": "run-001", "record_type": "RUN"}
        )

    @patch("lambdas.shared.dynamo.time.sleep")
    @patch("lambdas.shared.dynamo.boto3")
    def test_write_item_retries_on_failure(self, mock_boto3, mock_sleep):
        """PutItem fails twice then succeeds on third attempt."""
        mock_table = MagicMock()
        error_response = {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "Rate exceeded"}}
        mock_table.put_item.side_effect = [
            ClientError(error_response, "PutItem"),
            ClientError(error_response, "PutItem"),
            {"ResponseMetadata": {"HTTPStatusCode": 200}},
        ]
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = write_item("test-table", {"run_id": "run-002", "record_type": "AUDIT"})

        assert result == {"ResponseMetadata": {"HTTPStatusCode": 200}}
        assert mock_table.put_item.call_count == 3
        # Verify exponential backoff sleep was called
        assert mock_sleep.call_count == 2

    @patch("lambdas.shared.dynamo.time.sleep")
    @patch("lambdas.shared.dynamo.boto3")
    def test_write_item_exhausts_retries(self, mock_boto3, mock_sleep):
        """PutItem fails 3 times (max_retries) and raises ClientError."""
        mock_table = MagicMock()
        error_response = {"Error": {"Code": "InternalServerError", "Message": "Service unavailable"}}
        mock_table.put_item.side_effect = ClientError(error_response, "PutItem")
        mock_boto3.resource.return_value.Table.return_value = mock_table

        with pytest.raises(ClientError) as exc_info:
            write_item("test-table", {"run_id": "run-003", "record_type": "RUN"})

        assert exc_info.value.response["Error"]["Code"] == "InternalServerError"
        assert mock_table.put_item.call_count == 3


# ═══════════════════════════════════════════════════════════════════════════════
# models.py tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateRecordType:
    """Tests for validate_record_type() and VALID_RECORD_TYPES."""

    def test_validate_record_type_valid(self):
        """All 5 valid record types return True."""
        valid_types = ["RUN", "QC_METRICS", "PROVENANCE", "AUDIT", "CORRECTION"]
        for record_type in valid_types:
            assert validate_record_type(record_type) is True, (
                f"Expected True for valid record type {record_type!r}"
            )

    def test_validate_record_type_invalid(self):
        """Invalid strings return False."""
        invalid_types = [
            "run",           # lowercase
            "INVALID",       # not in set
            "",              # empty string
            "QC_METRIC",    # singular (typo)
            "AUDIT_LOG",    # wrong name
            "DELETE",        # not allowed
        ]
        for record_type in invalid_types:
            assert validate_record_type(record_type) is False, (
                f"Expected False for invalid record type {record_type!r}"
            )

    def test_valid_record_types_set(self):
        """VALID_RECORD_TYPES is exactly the expected set of 6 values."""
        expected = {"RUN", "QC_METRICS", "PROVENANCE", "AUDIT", "CORRECTION", "QC_WARNING"}
        assert VALID_RECORD_TYPES == expected


# ═══════════════════════════════════════════════════════════════════════════════
# audit.py tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildCompletionRecord:
    """Tests for build_completion_record()."""

    def test_build_completion_record_structure(self):
        """All required fields are present and correct."""
        record = build_completion_record(
            run_id="run-abc-123",
            sample_id="HG002",
            execution_start="2024-03-15T10:00:00Z",
            execution_end="2024-03-15T10:30:00Z",
        )

        assert record["run_id"] == "run-abc-123"
        assert record["record_type"] == "AUDIT"
        assert record["sample_id"] == "HG002"
        assert record["action"] == "WORKFLOW_COMPLETE"
        assert record["execution_start"] == "2024-03-15T10:00:00Z"
        assert record["execution_end"] == "2024-03-15T10:30:00Z"
        assert "created_at" in record
        assert ISO8601_PATTERN.match(record["created_at"])


class TestBuildFailureRecord:
    """Tests for build_failure_record()."""

    def test_build_failure_record_structure(self):
        """All required fields are present and correct."""
        record = build_failure_record(
            run_id="run-xyz-789",
            sample_id="HG002",
            failed_state="RunVariantCalling",
            error_cause="OOM killed by container runtime",
        )

        assert record["run_id"] == "run-xyz-789"
        assert record["record_type"] == "AUDIT"
        assert record["sample_id"] == "HG002"
        assert record["action"] == "WORKFLOW_FAILED"
        assert record["failed_state"] == "RunVariantCalling"
        assert record["error_cause"] == "OOM killed by container runtime"
        assert "created_at" in record
        assert ISO8601_PATTERN.match(record["created_at"])


class TestBuildAuditRecord:
    """Tests for build_audit_record()."""

    def test_build_audit_record_with_detail(self):
        """Detail dict is included when provided."""
        detail = {"f1_score": 0.985, "caller": "HaplotypeCaller"}
        record = build_audit_record(
            run_id="run-detail-001",
            sample_id="HG002",
            action="VALIDATION_FAILED",
            detail=detail,
        )

        assert record["run_id"] == "run-detail-001"
        assert record["record_type"] == "AUDIT"
        assert record["sample_id"] == "HG002"
        assert record["action"] == "VALIDATION_FAILED"
        assert record["detail"] == detail
        assert record["detail"]["f1_score"] == 0.985

    def test_build_audit_record_without_detail(self):
        """Detail is absent from record when not provided."""
        record = build_audit_record(
            run_id="run-no-detail-002",
            sample_id="HG002",
            action="INGESTION_STARTED",
        )

        assert record["run_id"] == "run-no-detail-002"
        assert record["record_type"] == "AUDIT"
        assert record["action"] == "INGESTION_STARTED"
        assert "detail" not in record

    def test_all_audit_records_have_created_at(self):
        """Every audit record type has a non-empty created_at timestamp."""
        records = [
            build_completion_record(
                run_id="run-ts-1",
                sample_id="HG002",
                execution_start="2024-01-01T00:00:00Z",
                execution_end="2024-01-01T01:00:00Z",
            ),
            build_failure_record(
                run_id="run-ts-2",
                sample_id="HG002",
                failed_state="ExportToS3",
                error_cause="Bucket not found",
            ),
            build_audit_record(
                run_id="run-ts-3",
                sample_id="HG002",
                action="REPORT_DRAFTED",
            ),
            build_audit_record(
                run_id="run-ts-4",
                sample_id="HG002",
                action="INGESTION_STARTED",
                detail={"source": "s3://bucket/raw/sample.fastq.gz"},
            ),
        ]

        for record in records:
            assert "created_at" in record, f"Record missing created_at: {record}"
            assert record["created_at"] != "", f"Record has empty created_at: {record}"
            assert ISO8601_PATTERN.match(record["created_at"]), (
                f"created_at {record['created_at']!r} does not match ISO 8601 pattern"
            )
