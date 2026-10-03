#!/usr/bin/env python3
"""QC Evaluation Script — evaluates all metrics against thresholds.

Reads fastp JSON, MarkDuplicates metrics, and hap.py summary, then evaluates
each metric against configured thresholds (adaptive or bootstrap). Outputs a
structured qc_warnings.json file with per-metric status and overall verdict.

Usage:
    qc_evaluate.py --sample HG002_chr20 \
        --fastp-json HG002.fastp.json \
        --dup-metrics HG002.markdup.metrics \
        --happy-summary HG002.happy.summary.csv \
        --thresholds-config /path/to/qc_thresholds.yaml \
        --output HG002.qc_warnings.json
"""
import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_fastp_json(path: str) -> dict[str, float]:
    """Extract QC metrics from fastp JSON output.

    Extracts:
      - q30_rate: fraction of bases with Q >= 30 (after filtering)
      - reads_filtered_percent: fraction of reads filtered out

    Args:
        path: Path to fastp JSON file.

    Returns:
        Dict with metric name → value.
    """
    with open(path) as fh:
        data = json.load(fh)

    metrics = {}

    # Q30 rate from filtering result (after filtering)
    summary = data.get("summary", {})
    after = summary.get("after_filtering", {})
    q30 = after.get("q30_rate")
    if q30 is not None:
        metrics["q30_rate"] = float(q30)

    # Reads filtered percent
    filtering = data.get("filtering_result", {})
    total = filtering.get("passed_filter_reads", 0) + filtering.get("low_quality_reads", 0) + \
            filtering.get("too_many_N_reads", 0) + filtering.get("too_short_reads", 0) + \
            filtering.get("too_long_reads", 0)
    if total > 0:
        filtered_out = total - filtering.get("passed_filter_reads", 0)
        metrics["reads_filtered_percent"] = filtered_out / total

    return metrics


def parse_dup_metrics(path: str) -> dict[str, float]:
    """Extract PERCENT_DUPLICATION from Picard MarkDuplicates metrics.

    Args:
        path: Path to .markdup.metrics file.

    Returns:
        Dict with percent_duplication value.
    """
    rows = []
    with open(path) as fh:
        header = None
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if header is None:
                header = fields
                continue
            if len(fields) == len(header):
                rows.append(dict(zip(header, fields)))

    if not rows:
        return {}

    pct = rows[0].get("PERCENT_DUPLICATION")
    if pct in (None, "", "?"):
        return {}
    return {"percent_duplication": float(pct)}


def parse_happy_summary(path: str) -> dict[str, float]:
    """Extract SNP precision, recall, F1 from hap.py summary CSV.

    Args:
        path: Path to .happy.summary.csv file.

    Returns:
        Dict with snp_f1, snp_precision, snp_recall.
    """
    metrics = {}
    with open(path) as fh:
        for row in csv.DictReader(fh):
            vtype = row.get("Type", "").upper()
            if vtype != "SNP":
                continue

            # hap.py column names vary by version
            def get_val(*keys):
                for k in keys:
                    if k in row and row[k] not in ("", "."):
                        return float(row[k])
                return None

            precision = get_val("METRIC.Precision", "Precision")
            recall = get_val("METRIC.Recall", "Recall")
            f1 = get_val("METRIC.F1_Score", "F1_Score")

            if precision is not None:
                metrics["snp_precision"] = precision
            if recall is not None:
                metrics["snp_recall"] = recall
            if f1 is not None:
                metrics["snp_f1"] = f1

    return metrics


def evaluate_metrics(
    metrics: dict[str, float],
    thresholds_config: dict,
) -> dict:
    """Evaluate all collected metrics against thresholds.

    Uses bootstrap thresholds from the config. Adaptive evaluation
    would require historical data (handled by the orchestration layer).

    Args:
        metrics: Dict of metric_name → observed_value.
        thresholds_config: Parsed YAML config dict with metrics section.

    Returns:
        Dict with per-metric evaluation and overall status.
    """
    configured_metrics = thresholds_config.get("metrics", {})
    results = {}
    overall_status = "pass"

    for name, value in metrics.items():
        if name not in configured_metrics:
            continue

        mconf = configured_metrics[name]
        direction = mconf["direction"]
        warn = float(mconf["warn"])
        fail = float(mconf["fail"])

        # Evaluate
        if direction == "higher_is_worse":
            if value > fail:
                status = "fail"
            elif value > warn:
                status = "warn"
            else:
                status = "pass"
        else:
            # lower_is_worse
            if value < fail:
                status = "fail"
            elif value < warn:
                status = "warn"
            else:
                status = "pass"

        results[name] = {
            "value": round(value, 6),
            "status": status,
            "warn_threshold": warn,
            "fail_threshold": fail,
            "direction": direction,
        }

        # Escalate overall status
        if status == "fail":
            overall_status = "fail"
        elif status == "warn" and overall_status != "fail":
            overall_status = "warn"

    return results, overall_status


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate QC metrics against thresholds")
    ap.add_argument("--sample", required=True, help="Sample identifier")
    ap.add_argument("--fastp-json", required=True, help="Path to fastp JSON output")
    ap.add_argument("--dup-metrics", required=True, help="Path to MarkDuplicates metrics")
    ap.add_argument("--happy-summary", required=True, help="Path to hap.py summary CSV")
    ap.add_argument("--thresholds-config", required=True, help="Path to qc_thresholds.yaml")
    ap.add_argument("--output", required=True, help="Output qc_warnings.json path")
    args = ap.parse_args()

    # Load thresholds config
    import yaml
    with open(args.thresholds_config) as fh:
        thresholds_config = yaml.safe_load(fh)

    # Collect metrics from all sources
    metrics: dict[str, float] = {}

    if Path(args.fastp_json).exists():
        metrics.update(parse_fastp_json(args.fastp_json))

    if Path(args.dup_metrics).exists():
        metrics.update(parse_dup_metrics(args.dup_metrics))

    if Path(args.happy_summary).exists():
        metrics.update(parse_happy_summary(args.happy_summary))

    # Evaluate all metrics
    per_metric_results, overall_status = evaluate_metrics(metrics, thresholds_config)

    # Build output document
    output = {
        "sample": args.sample,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "metrics": per_metric_results,
        "warnings": [
            name for name, r in per_metric_results.items() if r["status"] == "warn"
        ],
        "failures": [
            name for name, r in per_metric_results.items() if r["status"] == "fail"
        ],
    }

    with open(args.output, "w") as fh:
        json.dump(output, fh, indent=2, sort_keys=True)

    # Report to stdout
    n_warn = len(output["warnings"])
    n_fail = len(output["failures"])
    print(
        f"QC evaluation: {args.sample} → {overall_status} "
        f"({n_warn} warnings, {n_fail} failures)"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
