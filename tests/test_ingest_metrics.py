"""Unit tests for pipeline/bin/ingest_metrics.py's pure helpers.

Only `extract_warning_rows` is exercised here (dependency-free, no Postgres
needed) — it's the mapping from a qc_evaluate.py output document to the rows
DB_INGEST writes into the insert-only `qc_warnings` table. See
docs/FIXES-TODO.md for the history of this gap (QC_EVALUATE.out.warnings used
to be a dangling channel).
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(module_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


im = _load(ROOT / "pipeline" / "bin" / "ingest_metrics.py", "ingest_metrics")


def test_extract_warning_rows_skips_passing_metrics():
    doc = {
        "sample": "HG002_chr20",
        "evaluated_at": "2026-09-15T00:00:00+00:00",
        "overall_status": "pass",
        "metrics": {
            "q30_rate": {
                "value": 0.97,
                "status": "pass",
                "warn_threshold": 0.9,
                "fail_threshold": 0.85,
                "direction": "lower_is_worse",
            }
        },
        "warnings": [],
        "failures": [],
    }
    assert im.extract_warning_rows(doc) == []


def test_extract_warning_rows_maps_warn_and_fail_metrics():
    doc = {
        "sample": "HG002_chr20",
        "evaluated_at": "2026-09-15T00:00:00+00:00",
        "overall_status": "fail",
        "metrics": {
            "percent_duplication": {
                "value": 0.09,
                "status": "warn",
                "warn_threshold": 0.08,
                "fail_threshold": 0.12,
                "direction": "higher_is_worse",
            },
            "snp_f1": {
                "value": 0.97,
                "status": "fail",
                "warn_threshold": 0.99,
                "fail_threshold": 0.98,
                "direction": "lower_is_worse",
            },
            "q30_rate": {
                "value": 0.97,
                "status": "pass",
                "warn_threshold": 0.9,
                "fail_threshold": 0.85,
                "direction": "lower_is_worse",
            },
        },
        "warnings": ["percent_duplication"],
        "failures": ["snp_f1"],
    }
    rows = im.extract_warning_rows(doc)
    assert len(rows) == 2

    by_metric = {r["metric_name"]: r for r in rows}
    dup_row = by_metric["percent_duplication"]
    assert dup_row["overall_status"] == "warn"
    assert dup_row["metric_value"] == 0.09
    assert dup_row["threshold_warn"] == 0.08
    assert dup_row["threshold_fail"] == 0.12
    # qc_evaluate.py only evaluates bootstrap thresholds today; asserting this
    # stays honest if adaptive thresholds are wired in later (the source
    # should then vary rather than being hard-coded).
    assert dup_row["threshold_source"] == "bootstrap"
    assert dup_row["metrics_detail"]["direction"] == "higher_is_worse"
    assert dup_row["metrics_detail"]["evaluated_at"] == doc["evaluated_at"]

    f1_row = by_metric["snp_f1"]
    assert f1_row["overall_status"] == "fail"


def test_extract_warning_rows_empty_metrics_is_noop():
    """Matches the stub qc_evaluate.nf output used under -stub."""
    doc = {"sample": "s", "overall_status": "pass", "metrics": {}, "warnings": [], "failures": []}
    assert im.extract_warning_rows(doc) == []
