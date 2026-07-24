"""Tests for the Validation Checker Lambda.

The F1 >= 0.99 threshold is the platform's acceptance criterion (ADR-0003), and
a failed validation must leave an audit trail — so these tests pin the boundary
behaviour and the AUDIT write, not just the happy path.

_simulate_validation_metrics() always returns ~0.998, so failure paths are
exercised by patching it rather than hoping for a low roll.
"""

import json
from unittest.mock import patch

import pytest

from lambdas.validation_checker.handler import (
    F1_PASS_THRESHOLD,
    _simulate_validation_metrics,
    handler,
)

_EVENT = {
    "run_id": "run_test_001",
    "sample_id": "HG002",
    "vcf_key": "work/run_test_001/variants/HG002.vcf.gz",
    "caller": "HaplotypeCaller",
    "n_variants": 4321,
}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DATA_LAKE_BUCKET", "test-bucket")
    monkeypatch.setenv("METADATA_TABLE", "test-metadata")


@pytest.fixture
def mocks():
    """Patch the two side-effecting calls: S3 write and DynamoDB write."""
    with (
        patch("lambdas.validation_checker.handler.write_json") as write_json,
        patch("lambdas.validation_checker.handler.write_item") as write_item,
    ):
        yield {"write_json": write_json, "write_item": write_item}


def _with_f1(f1: float):
    """Force the simulated metrics to a specific F1."""
    return patch(
        "lambdas.validation_checker.handler._simulate_validation_metrics",
        return_value={"precision": f1, "recall": f1, "f1": f1},
    )


class TestSimulatedMetrics:
    def test_metrics_are_self_consistent(self):
        """f1 must be the harmonic mean of the precision/recall it ships with."""
        m = _simulate_validation_metrics()
        expected = 2 * (m["precision"] * m["recall"]) / (m["precision"] + m["recall"])
        assert m["f1"] == pytest.approx(expected, abs=1e-6)

    def test_metrics_are_in_clinical_range(self):
        m = _simulate_validation_metrics()
        assert 0.99 < m["precision"] <= 1.0
        assert 0.99 < m["recall"] <= 1.0


class TestThreshold:
    def test_f1_above_threshold_passes(self, mocks):
        with _with_f1(0.9995):
            result = handler(dict(_EVENT), None)
        assert result["validation_pass"] is True

    def test_f1_exactly_at_threshold_passes(self, mocks):
        """The criterion is F1 >= 0.99, so the boundary itself must pass."""
        with _with_f1(F1_PASS_THRESHOLD):
            result = handler(dict(_EVENT), None)
        assert result["validation_pass"] is True

    def test_f1_just_below_threshold_fails(self, mocks):
        with _with_f1(0.9899):
            result = handler(dict(_EVENT), None)
        assert result["validation_pass"] is False


class TestAuditTrail:
    def test_failure_writes_audit_record(self, mocks):
        with _with_f1(0.95):
            handler(dict(_EVENT), None)

        mocks["write_item"].assert_called_once()
        table, record = mocks["write_item"].call_args[0]
        assert table == "test-metadata"
        assert record["action"] == "VALIDATION_FAILED"
        assert record["detail"]["f1"] == 0.95
        assert record["detail"]["threshold"] == F1_PASS_THRESHOLD

    def test_success_writes_no_audit_record(self, mocks):
        """A passing run must not pollute the audit log."""
        with _with_f1(0.9995):
            handler(dict(_EVENT), None)
        mocks["write_item"].assert_not_called()


class TestResultsWrite:
    def test_results_written_to_run_scoped_key(self, mocks):
        with _with_f1(0.9995):
            handler(dict(_EVENT), None)

        bucket, key, payload = mocks["write_json"].call_args[0]
        assert bucket == "test-bucket"
        assert key == "work/run_test_001/validation/results.json"
        assert payload["snp"]["f1"] == 0.9995
        assert payload["validation_pass"] is True
        assert payload["caller"] == "HaplotypeCaller"

    def test_results_are_json_serialisable(self, mocks):
        """The payload goes to S3 as JSON — no numpy/Decimal leakage."""
        with _with_f1(0.9995):
            handler(dict(_EVENT), None)
        payload = mocks["write_json"].call_args[0][2]
        json.dumps(payload)


class TestReturnContract:
    def test_returns_expected_fields(self, mocks):
        with _with_f1(0.9995):
            result = handler(dict(_EVENT), None)
        assert set(result) == {
            "run_id",
            "sample_id",
            "precision",
            "recall",
            "f1",
            "validation_pass",
        }
        assert result["run_id"] == "run_test_001"
        assert result["sample_id"] == "HG002"

    def test_optional_event_fields_default(self, mocks):
        """vcf_key/caller/n_variants are optional on the Step Functions payload."""
        minimal = {"run_id": "run_min", "sample_id": "HG002"}
        with _with_f1(0.9995):
            handler(minimal, None)
        payload = mocks["write_json"].call_args[0][2]
        assert payload["caller"] == "HaplotypeCaller"
        assert payload["n_variants"] == 0
        assert payload["vcf_key"] == ""

    @pytest.mark.parametrize("missing", ["run_id", "sample_id"])
    def test_missing_required_field_raises(self, mocks, missing):
        event = {k: v for k, v in _EVENT.items() if k != missing}
        with _with_f1(0.9995), pytest.raises(KeyError):
            handler(event, None)
