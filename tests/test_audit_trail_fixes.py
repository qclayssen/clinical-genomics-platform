"""Regression tests for the 2026-09-24 audit findings on the serverless path.

- Audit events persisted under per-event sort keys (lambdas/shared/dynamo.py)
  must still be grouped as one AUDIT list by the DynamoDB→Postgres sync.
- The Lambda export's provenance must use the key the report renderer and
  guardrail read (`truth_version`), and carry the `simulated` marker so a
  synthetic F1 is never presented as measured.
"""
from db.sync_dynamodb_to_postgres import group_by_run_id
from lambdas.export_handler.handler import _build_metrics as build_metrics_json


def test_sync_groups_per_event_audit_keys_into_one_list():
    items = [
        {"run_id": "r1", "record_type": "RUN"},
        {"run_id": "r1", "record_type": "AUDIT#2026-09-24T00:00:00Z#REPORT_DRAFTED#a1"},
        {"run_id": "r1", "record_type": "AUDIT#2026-09-24T00:00:01Z#WORKFLOW_COMPLETE#b2"},
        {"run_id": "r1", "record_type": "AUDIT"},  # legacy single-key item
    ]
    grouped = group_by_run_id(items)
    assert len(grouped["r1"]["AUDIT"]) == 3
    assert "RUN" in grouped["r1"]


def test_export_provenance_uses_truth_version_key():
    metrics = build_metrics_json({"f1": 0.99, "simulated": True})
    assert metrics["provenance"]["truth_version"] == "GIAB_v4.2.1_HG002_chr20"
    assert "truth_set_version" not in metrics["provenance"]


def test_export_carries_simulated_marker_defaulting_to_true():
    assert build_metrics_json({})["simulated"] is True
    assert build_metrics_json({"simulated": False})["simulated"] is False


def test_offline_report_never_presents_simulated_f1_as_a_pass():
    import sys
    from pathlib import Path

    ai_report = str(Path(__file__).resolve().parents[1] / "ai-report")
    if ai_report not in sys.path:
        sys.path.insert(0, ai_report)
    import infer

    metrics = build_metrics_json({"f1": 0.995, "precision": 0.99, "recall": 0.99,
                                  "validation_pass": True, "simulated": True})
    report = infer.render_offline(metrics)
    assert "met the F1" not in report
    assert "SIMULATED" in report

    measured = build_metrics_json({"f1": 0.995, "validation_pass": True, "simulated": False})
    assert "met the F1 ≥ 0.99 acceptance threshold" in infer.render_offline(measured)


# ═══ DynamoDB→Postgres sync must not fabricate provenance ═══
# Missing fields used to be filled with invented values ("unknown" commit,
# "HaplotypeCaller", "0.0.0", F1 0.0) in insert-only tables that can never be
# corrected afterwards.

class _RecordingCursor:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchone(self):
        return None


def test_sync_skips_run_with_missing_required_provenance():
    from db.sync_dynamodb_to_postgres import sync_run

    records = {"RUN": {"run_id": "r1", "sample_id": "HG002_chr20", "validation_pass": True}}
    result = sync_run(_RecordingCursor(), "r1", records)
    assert result["status"] == "skipped"
    for field in ("pipeline_version", "git_commit", "caller"):
        assert field in result["reason"]


def test_sync_stores_missing_qc_numbers_as_null_not_zero():
    from db.sync_dynamodb_to_postgres import _insert_qc_metrics

    cur = _RecordingCursor()
    _insert_qc_metrics(cur, 1, {"snp_f1": 0.99})
    _, params = cur.calls[0]
    assert params == (1, None, None, None, 0.99, None)


def test_sync_takes_reference_build_from_provenance_when_run_lacks_it():
    from db.sync_dynamodb_to_postgres import _reference_build

    assert _reference_build({"RUN": {}, "PROVENANCE": {"reference_build": "GRCh38"}}) == "GRCh38"
    assert _reference_build({"RUN": {"reference_build": "GRCh37"}, "PROVENANCE": {}}) == "GRCh37"
    assert _reference_build({"RUN": {}}) is None
