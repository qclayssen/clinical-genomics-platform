"""Report Generator Lambda.

Reads metrics.json from S3, generates an AI-drafted report (RAG-augmented or
offline fallback), applies guardrails, writes the report to S3, and records
audit trail entries for REPORT_DRAFTED and WORKFLOW_COMPLETE.

Requirements: 9.4, 9.6, 9.7, 11.3
"""

import json
import logging
import os
import sys
from pathlib import Path

from lambdas.shared.audit import build_audit_record, build_completion_record
from lambdas.shared.dynamo import write_item
from lambdas.shared.s3_utils import read_json, write_bytes
from lambdas.shared.timestamps import now_iso8601

# `ai-report/` isn't a package root (see api/routers/agent.py for the same
# pattern), so its shared `guardrails` module is reached via sys.path, not a
# normal package import. AI_REPORT_PATH lets a real Lambda deployment point
# at wherever the ai-report code is bundled (e.g. a layer at /opt/ai-report,
# matching the RAG path below); locally/in tests it resolves to the sibling
# ai-report/ directory in this repo.
_DEFAULT_AI_REPORT_DIR = str(Path(__file__).resolve().parents[2] / "ai-report")
_AI_REPORT_DIR = os.environ.get("AI_REPORT_PATH", _DEFAULT_AI_REPORT_DIR)
if not os.path.isdir(_AI_REPORT_DIR) and os.path.isdir(_DEFAULT_AI_REPORT_DIR):
    _AI_REPORT_DIR = _DEFAULT_AI_REPORT_DIR
if _AI_REPORT_DIR not in sys.path:
    sys.path.insert(0, _AI_REPORT_DIR)

from guardrails import BANNER, enforce_guardrails  # noqa: E402

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Model versioning defaults
_MODEL_VERSION = os.environ.get("MODEL_VERSION", "phi3:mini")
_ADAPTER_VERSION = os.environ.get("ADAPTER_VERSION", None)


# ---------------------------------------------------------------------------
# Offline renderer (stdlib only; BANNER/enforce_guardrails come from the
# shared ai-report/guardrails module resolved above)
# ---------------------------------------------------------------------------


def render_offline(m: dict) -> str:
    """Deterministic, dependency-free renderer. Always guardrail-compliant.

    Mirrors the logic in ai-report/infer.py's render_offline(); kept as its
    own copy (rather than imported) since it has no shared-state risk the way
    the guardrail scrub list did — a rendering-template drift is cosmetic,
    not a guardrail-consistency bug. Only the guardrail enforcement itself
    (BANNER, enforce_guardrails) is imported from `guardrails.py`.
    """
    snp = m.get("validation", {}).get("snp", {})
    prov = m.get("provenance", {})
    p = snp.get("precision")
    r = snp.get("recall")
    f1 = snp.get("f1")
    dup = m.get("qc", {}).get("percent_duplication")
    passed = m.get("validation_pass")
    nvar = prov.get("n_variants")

    def pct(x):
        return f"{x * 100:.1f}%" if isinstance(x, (int, float)) else "n/a"

    verdict = (
        "The run met the F1 \u2265 0.99 acceptance threshold."
        if passed
        else "The run did NOT meet the acceptance threshold; results should not be used "
        "until reviewed by a clinician."
    )
    lines = [
        BANNER,
        "",
        f"Sample {m.get('sample', '?')} was processed with the "
        f"{prov.get('caller', '?')} variant caller. {verdict}",
        f"SNV precision {pct(p)} (validation.snp.precision), "
        f"recall {pct(r)} (validation.snp.recall), "
        f"F1 {pct(f1)} (validation.snp.f1).",
    ]
    if nvar is not None:
        lines.append(f"{nvar:,} variants were called (provenance.n_variants).")
    if dup is not None:
        lines.append(
            f"Duplication rate {pct(dup)} (qc.percent_duplication) as a "
            "library-quality indicator."
        )
    lines.append("No clinical interpretation of individual variants is provided.")
    lines.append("")
    lines.append(
        f"Provenance: git {prov.get('git_commit', '?')}, "
        f"{prov.get('truth_version', '?')}."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# RAG generation attempt
# ---------------------------------------------------------------------------


def _try_rag_generation(m: dict) -> str | None:
    """Attempt RAG-augmented report generation.

    Returns the generated report text, or None if the RAG path is unavailable.
    This imports the ai-report module at runtime; if unavailable (e.g., in
    Lambda container without the ai-report package), returns None.
    """
    try:
        # ai-report/ was already added to sys.path above (for `guardrails`);
        # reuse the same resolved directory here for consistency.
        from infer import render_with_rag  # type: ignore[import-not-found]

        index_dir = os.environ.get("RAG_INDEX_DIR", "/opt/ai-report/rag/index")
        ollama_model = os.environ.get("OLLAMA_MODEL", "phi3:mini")

        report = render_with_rag(m, index_dir, ollama_model)
        return report
    except Exception as exc:
        logger.warning(
            json.dumps(
                {
                    "level": "WARNING",
                    "function": "report_generator",
                    "message": f"RAG generation unavailable: {exc}",
                    "timestamp": now_iso8601(),
                }
            )
        )
        return None


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------


def handler(event: dict, context) -> dict:
    """Lambda entry point for report generation.

    Receives the Step Functions payload, reads metrics from S3, generates a
    report (RAG or offline fallback), applies guardrails, writes the report
    to S3, and records audit entries.

    Args:
        event: Step Functions payload with keys:
            - run_id (str)
            - sample_id (str)
            - export_key (str): S3 key for metrics.json
        context: Lambda context (unused).

    Returns:
        Dict with run_id, sample_id, and report_key.
    """
    run_id = event["run_id"]
    sample_id = event.get("sample_id", "")
    export_key = event["export_key"]
    bucket = os.environ["DATA_LAKE_BUCKET"]
    table_name = os.environ["METADATA_TABLE"]

    execution_start = event.get("execution_start", now_iso8601())

    logger.info(
        json.dumps(
            {
                "level": "INFO",
                "run_id": run_id,
                "function": "report_generator",
                "message": "Reading metrics.json from S3",
                "timestamp": now_iso8601(),
            }
        )
    )

    # 1. Read metrics.json from S3
    metrics = read_json(bucket, export_key)

    # 2. Try RAG generation, fall back to offline template
    report = _try_rag_generation(metrics)
    generation_method = "rag"

    if report is None:
        logger.info(
            json.dumps(
                {
                    "level": "INFO",
                    "run_id": run_id,
                    "function": "report_generator",
                    "message": "Falling back to offline template renderer",
                    "timestamp": now_iso8601(),
                }
            )
        )
        report = render_offline(metrics)
        generation_method = "offline"

    # 3. Apply guardrails enforcement
    report = enforce_guardrails(report, metrics)

    logger.info(
        json.dumps(
            {
                "level": "INFO",
                "run_id": run_id,
                "function": "report_generator",
                "message": f"Report generated via {generation_method}, guardrails applied",
                "timestamp": now_iso8601(),
            }
        )
    )

    # 4. Write report to S3
    report_key = f"results/{run_id}/report.txt"
    write_bytes(
        bucket, report_key, report.encode("utf-8"), content_type="text/plain"
    )

    logger.info(
        json.dumps(
            {
                "level": "INFO",
                "run_id": run_id,
                "function": "report_generator",
                "message": f"Report written to s3://{bucket}/{report_key}",
                "timestamp": now_iso8601(),
            }
        )
    )

    # 5. Write AUDIT record: REPORT_DRAFTED
    adapter_version = _ADAPTER_VERSION if generation_method == "rag" else None
    report_drafted_record = build_audit_record(
        run_id=run_id,
        sample_id=sample_id,
        action="REPORT_DRAFTED",
        detail={
            "model_version": _MODEL_VERSION,
            "adapter_version": adapter_version,
            "generation_method": generation_method,
        },
    )
    write_item(table_name, report_drafted_record)

    logger.info(
        json.dumps(
            {
                "level": "INFO",
                "run_id": run_id,
                "function": "report_generator",
                "message": "AUDIT record REPORT_DRAFTED written to DynamoDB",
                "timestamp": now_iso8601(),
            }
        )
    )

    # 6. Write AUDIT record: WORKFLOW_COMPLETE
    execution_end = now_iso8601()
    completion_record = build_completion_record(
        run_id=run_id,
        sample_id=sample_id,
        execution_start=execution_start,
        execution_end=execution_end,
    )
    write_item(table_name, completion_record)

    logger.info(
        json.dumps(
            {
                "level": "INFO",
                "run_id": run_id,
                "function": "report_generator",
                "message": "AUDIT record WORKFLOW_COMPLETE written to DynamoDB",
                "timestamp": now_iso8601(),
            }
        )
    )

    return {
        "run_id": run_id,
        "sample_id": sample_id,
        "report_key": report_key,
    }
