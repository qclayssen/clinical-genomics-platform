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


def count_variants(vcf: str) -> int:
    try:
        out = subprocess.run(
            ["bcftools", "view", "-H", vcf],
            capture_output=True, text=True, check=True,
        )
        return sum(1 for _ in out.stdout.splitlines())
    except Exception:
        return -1  # bcftools unavailable in this image; recorded as unknown


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", required=True)
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--vcf", required=True)
    ap.add_argument("--log", required=True)
    args = ap.parse_args()

    with open(args.metrics) as fh:
        rec = json.load(fh)
    prov = rec["provenance"]
    n_variants = count_variants(args.vcf)

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
            # 5. audit trail
            cur.execute(
                """INSERT INTO audit_log (run_pk, action, detail)
                   VALUES (%s, 'INGEST', %s)""",
                (run_pk, f"ingested {rec['sample']} run {prov['run_id']}"),
            )
        conn.commit()
        msg = f"ingested {rec['sample']} run {prov['run_id']} ({n_variants} variants)"
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
