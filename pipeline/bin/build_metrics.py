#!/usr/bin/env python3
"""Assemble the structured metrics.json for one sample.

This is the traceability heart of the pipeline: it merges QC + validation metrics
with a provenance stamp (git commit, tool/reference versions, SHA-256 of every
input file) into a single insert-only record. Mirrors the record a clinical lab
keeps for each run under ISO 15189 traceability requirements.
"""
import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_dup_metrics(path: str) -> dict:
    """Extract PERCENT_DUPLICATION from a Picard/GATK MarkDuplicates metrics file."""
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
    return {"percent_duplication": float(pct) if pct not in (None, "", "?") else None}


def parse_happy(path: str) -> dict:
    """Extract precision/recall/F1 for SNP and INDEL from a hap.py summary.csv."""
    out = {}
    with open(path) as fh:
        for row in csv.DictReader(fh):
            vtype = row.get("Type", "").upper()
            if vtype not in ("SNP", "INDEL"):
                continue
            # hap.py column names vary slightly by version; probe both forms
            def g(*keys):
                for k in keys:
                    if k in row and row[k] not in ("", "."):
                        return float(row[k])
                return None
            out[vtype.lower()] = {
                "precision": g("METRIC.Precision", "Precision"),
                "recall": g("METRIC.Recall", "Recall"),
                "f1": g("METRIC.F1_Score", "F1_Score"),
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True)
    ap.add_argument("--dup-metrics", required=True)
    ap.add_argument("--happy-summary", required=True)
    ap.add_argument("--provenance", required=True, help="JSON string")
    ap.add_argument("--inputs", required=True, help="comma-separated input files to checksum")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    provenance = json.loads(args.provenance)
    provenance["exported_at"] = datetime.now(timezone.utc).isoformat()
    provenance["input_checksums"] = {
        Path(p).name: sha256(p) for p in args.inputs.split(",") if p and Path(p).exists()
    }

    happy = parse_happy(args.happy_summary)
    snp_f1 = (happy.get("snp") or {}).get("f1")

    record = {
        "sample": args.sample,
        "schema_version": "1.0",
        "qc": parse_dup_metrics(args.dup_metrics),
        "validation": happy,
        # Acceptance criterion, evaluated here so the DB/dashboard can trust it
        "validation_pass": bool(snp_f1 is not None and snp_f1 >= 0.99),
        "provenance": provenance,
    }

    with open(args.output, "w") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
    print(f"wrote {args.output} (validation_pass={record['validation_pass']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
