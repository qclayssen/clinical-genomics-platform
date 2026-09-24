#!/usr/bin/env python3
"""Ingest a sample's metrics.json into Postgres.

Every insert is append-only and writes an audit_log row. There is deliberately no
UPDATE/DELETE path — corrections are new rows, mirroring how a clinical record is
amended rather than overwritten.
"""
import argparse
import json
import subprocess
import sys


def extract_warning_rows(qc_doc: dict) -> list[dict]:
    """Flatten a qc_evaluate.py output document into qc_warnings row dicts.

    Only metrics that breached a threshold (status "warn" or "fail") become a
    row — the `qc_warnings` table records breaches, not clean metrics. See
    `pipeline/bin/qc_evaluate.py` for the input document shape.

    `threshold_source` is hard-coded to "bootstrap": `qc_evaluate.py` only
    ever evaluates against the static bootstrap thresholds in
    `conf/qc_thresholds.yaml` today — adaptive (mean +/- sigma) thresholds are
    computed by `qc_adaptive.py` but not yet wired into this script. Recording
    "bootstrap" here is honest about that gap rather than implying adaptive
    thresholds are already in effect.
    """
    rows = []
    for name, m in qc_doc.get("metrics", {}).items():
        status = m.get("status")
        if status not in ("warn", "fail"):
            continue
        rows.append(
            {
                "metric_name": name,
                "overall_status": status,
                "metric_value": m.get("value"),
                "threshold_warn": m.get("warn_threshold"),
                "threshold_fail": m.get("fail_threshold"),
                "threshold_source": "bootstrap",
                "metrics_detail": {
                    "direction": m.get("direction"),
                    "evaluated_at": qc_doc.get("evaluated_at"),
                },
            }
        )
    return rows


def count_variants(vcf: str) -> int | None:
    """Count VCF records, or None when bcftools is unavailable or fails —
    stored as NULL (unknown), never as a made-up number in an insert-only row."""
    try:
        out = subprocess.run(
            ["bcftools", "view", "-H", vcf],
            capture_output=True, text=True, check=True,
        )
        return sum(1 for _ in out.stdout.splitlines())
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"ingest_metrics: could not count variants in {vcf}: {exc}", file=sys.stderr)
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", required=True)
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--qc-warnings", required=True)
    ap.add_argument("--vcf", required=True)
    ap.add_argument("--log", required=True)
    args = ap.parse_args()

    with open(args.metrics) as fh:
        rec = json.load(fh)
    prov = rec["provenance"]
    n_variants = count_variants(args.vcf)
    if n_variants is None:
        n_variants = prov.get("n_variants")  # the stamp's own count, if it has one

    with open(args.qc_warnings) as fh:
        qc_doc = json.load(fh)
    warning_rows = extract_warning_rows(qc_doc)

    import psycopg2  # imported here so --help works without the driver

    conn = psycopg2.connect(args.db_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # 1. sample (idempotent on natural key)
            cur.execute(
                """INSERT INTO samples (sample_id, reference_build)
                   VALUES (%s, %s)
                   ON CONFLICT (sample_id) DO NOTHING""",
                (rec["sample"], prov.get("reference_build")),
            )
            # 2. run (insert-only; one row per pipeline execution)
            cur.execute(
                """INSERT INTO runs
                     (run_id, sample_id, pipeline_version, git_commit, caller,
                      started_at, exported_at, validation_pass)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id""",
                (prov["run_id"], rec["sample"], prov.get("pipeline_version"),
                 prov.get("git_commit"), prov.get("caller"),
                 prov.get("started_at"), prov.get("exported_at"),
                 rec["validation_pass"]),
            )
            run_pk = cur.fetchone()[0]
            # 3. qc + validation metrics
            snp = rec["validation"].get("snp", {})
            cur.execute(
                """INSERT INTO qc_metrics
                     (run_pk, percent_duplication, snp_precision, snp_recall,
                      snp_f1, n_variants)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (run_pk, rec["qc"].get("percent_duplication"),
                 snp.get("precision"), snp.get("recall"), snp.get("f1"),
                 n_variants),
            )
            # 4. provenance (checksums as JSONB, insert-only)
            cur.execute(
                """INSERT INTO run_provenance (run_pk, input_checksums, truth_version)
                   VALUES (%s, %s, %s)""",
                (run_pk, json.dumps(prov.get("input_checksums", {})),
                 prov.get("truth_version")),
            )
            # 5. qc_warnings (one row per threshold breach; insert-only)
            for row in warning_rows:
                cur.execute(
                    """INSERT INTO qc_warnings
                         (run_pk, sample_id, overall_status, metric_name,
                          metric_value, threshold_warn, threshold_fail,
                          threshold_source, metrics_detail)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (run_pk, rec["sample"], row["overall_status"],
                     row["metric_name"], row["metric_value"],
                     row["threshold_warn"], row["threshold_fail"],
                     row["threshold_source"], json.dumps(row["metrics_detail"])),
                )
            # 6. audit trail
            cur.execute(
                """INSERT INTO audit_log (run_pk, action, detail)
                   VALUES (%s, 'INGEST', %s)""",
                (run_pk, f"ingested {rec['sample']} run {prov['run_id']}"),
            )
        conn.commit()
        msg = (
            f"ingested {rec['sample']} run {prov['run_id']} "
            f"({n_variants} variants, {len(warning_rows)} qc_warnings)"
        )
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        msg = f"FAILED: {exc}"
        with open(args.log, "w") as fh:
            fh.write(msg + "\n")
        conn.close()
        raise
    finally:
        conn.close()

    with open(args.log, "w") as fh:
        fh.write(msg + "\n")
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
