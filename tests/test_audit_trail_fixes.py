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
