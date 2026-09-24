#!/usr/bin/env python3
"""Derive the agent-evaluation gold set from the committed chr20 knowledge base.

The gold set is *derived*, not hand-typed, so that it can never silently drift
from the knowledge base the agent actually queries. ``tests/test_agent_eval.py``
re-runs this derivation and fails if the committed ``gold_set.jsonl`` differs.

Rows carry a ``tier``:

* ``gold``   — ClinVar review status >= 2 stars (multiple submitters with no
               conflicts, expert panel, or practice guideline). Scored and gated.
* ``silver`` — ClinVar 1 star (single submitter). Scored and reported, never gated:
               a single-submitter assertion is not a trustworthy reference label.
* ``probe``  — no ClinVar record in the KB. There is **no** expected
               classification; these rows exist only to measure hallucinated
               citations and tool grounding (an agent that "finds" a ClinVar
               record for one of these is fabricating it).

Usage:
    python ai-report/eval/build_gold_set.py            # rewrite gold_set.jsonl
    python ai-report/eval/build_gold_set.py --check    # exit 1 if the committed file is stale
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent
_AI_REPORT_DIR = _EVAL_DIR.parent
DEFAULT_DB = _AI_REPORT_DIR / "agent" / "data" / "chr20_knowledge.db"
DEFAULT_OUT = _EVAL_DIR / "gold_set.jsonl"

# ClinVar review statuses that ClinVar itself rates >= 2 stars. Eligibility is
# decided on the status string, not the KB's ``review_stars`` column, because the
# KB stores the multi-submitter status as 3 where ClinVar's scale says 2.
GOLD_REVIEW_STATUSES = frozenset({
    "criteria_provided_multiple_submitters_no_conflicts",  # 2 stars
    "reviewed_by_expert_panel",                           # 3 stars
    "practice_guideline",                                 # 4 stars
})

# ClinVar's own star scale, by review-status string (the KB column is shifted).
_CLINVAR_STARS = {
    "practice_guideline": 4,
    "reviewed_by_expert_panel": 3,
    "criteria_provided_multiple_submitters_no_conflicts": 2,
    "criteria_provided_single_submitter": 1,
    "criteria_provided_conflicting_interpretations": 1,
}

# ClinVar significance string (as stored in the KB) -> 5-class code.
_SIG_TO_CLASS = {
    "Pathogenic": "P",
    "Likely Pathogenic": "LP",
    "Uncertain Significance": "VUS",
    "Likely Benign": "LB",
    "Benign": "B",
}

# Negative-control probes. Coordinates are *synthetic*: chosen inside annotated
# chr20 genes (chr20_genes.bed) or taken from the KB's gnomAD-only rows, and
# confirmed absent from the KB's ClinVar table at build time (asserted below).
# They carry no expected classification.
_PROBES = [
    # gnomAD-only rows already in the KB (common / filtered variants, no ClinVar record)
    {"chrom": "chr20", "pos": 1234567, "ref": "A", "alt": "G", "gene": "",
     "note": "gnomAD-only KB row (AF 0.12); no ClinVar record"},
    {"chrom": "chr20", "pos": 9876543, "ref": "T", "alt": "C", "gene": "",
     "note": "gnomAD-only KB row (AF 0.25); no ClinVar record"},
    {"chrom": "chr20", "pos": 5555555, "ref": "G", "alt": "T", "gene": "",
     "note": "gnomAD-only KB row (AF 0.001, filter AC0); no ClinVar record"},
    # Absent from both tables: synthetic positions inside annotated genes
    {"chrom": "chr20", "pos": 4690000, "ref": "C", "alt": "G", "gene": "PRNP",
     "note": "synthetic position in PRNP; absent from ClinVar and gnomAD tables"},
    {"chrom": "chr20", "pos": 10600000, "ref": "A", "alt": "T", "gene": "JAG1",
     "note": "synthetic position in JAG1; absent from ClinVar and gnomAD tables"},
    {"chrom": "chr20", "pos": 39650000, "ref": "G", "alt": "C", "gene": "TOP1",
     "note": "synthetic position in TOP1; absent from ClinVar and gnomAD tables"},
]


def _kb_metadata(conn: sqlite3.Connection) -> dict[str, str]:
    return {k: v for k, v in conn.execute("SELECT key, value FROM metadata")}


def build_rows(db_path: Path = DEFAULT_DB) -> list[dict]:
    """Return the gold-set rows derived from the KB, in a stable order."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        meta = _kb_metadata(conn)
        source = f"{meta.get('clinvar_source', 'unknown')} (KB v{meta.get('version', '?')})"
        clinvar = conn.execute(
            "SELECT * FROM clinvar ORDER BY review_stars DESC, chrom, pos, ref, alt"
        ).fetchall()

        rows: list[dict] = []
        for r in clinvar:
            rows.append({
                "id": f"{r['gene']}:{r['hgvs_p'] or r['pos']}",
                "tier": "gold" if r["review_status"] in GOLD_REVIEW_STATUSES else "silver",
                "chrom": r["chrom"],
                "pos": int(r["pos"]),
                "ref": r["ref"],
                "alt": r["alt"],
                "gene": r["gene"],
                "hgvs_p": r["hgvs_p"],
                "expected_class": _SIG_TO_CLASS[r["clinical_significance"]],
                "clinvar_significance": r["clinical_significance"],
                "clinvar_variation_id": r["variant_id"],
                "review_status": r["review_status"],
                "clinvar_review_stars": _CLINVAR_STARS.get(r["review_status"], 0),
                "source": source,
            })

        for p in _PROBES:
            hit = conn.execute(
                "SELECT 1 FROM clinvar WHERE chrom=? AND pos=? AND ref=? AND alt=?",
                (p["chrom"], p["pos"], p["ref"], p["alt"]),
            ).fetchone()
            if hit:
                raise ValueError(f"probe {p} unexpectedly has a ClinVar record in the KB")
            rows.append({
                "id": f"probe:{p['chrom']}:{p['pos']}{p['ref']}>{p['alt']}",
                "tier": "probe",
                "chrom": p["chrom"],
                "pos": p["pos"],
                "ref": p["ref"],
                "alt": p["alt"],
                "gene": p["gene"],
                "hgvs_p": None,
                "expected_class": None,
                "clinvar_significance": None,
                "clinvar_variation_id": None,
                "review_status": None,
                "clinvar_review_stars": 0,
                "source": f"negative control — {p['note']}",
            })
        return rows
    finally:
        conn.close()


def render_jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true",
                    help="Do not write; exit 1 if --out differs from the derivation")
    args = ap.parse_args(argv)

    text = render_jsonl(build_rows(args.db))
    if args.check:
        current = args.out.read_text() if args.out.exists() else ""
        if current != text:
            print(f"{args.out} is stale — rerun build_gold_set.py", file=sys.stderr)
            return 1
        print(f"{args.out} is up to date")
        return 0
    args.out.write_text(text)
    print(f"wrote {args.out} ({text.count(chr(10))} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
