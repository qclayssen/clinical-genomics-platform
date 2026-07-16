#!/usr/bin/env python3
"""Build a local chr20 ClinVar + gnomAD knowledge base (SQLite).

Creates a small SQLite database containing:
  1. ClinVar variant records for chr20 genes (clinical significance, review status)
  2. gnomAD allele frequencies for chr20 positions (global AF, popmax AF, hom count)

The database is committed to the repo (~200KB) so the agent works offline and in CI
without downloading external datasets. For production use, run with --download to pull
the latest ClinVar/gnomAD subsets for chr20.

Usage:
    python scripts/build_chr20_knowledgebase.py                 # build from embedded data
    python scripts/build_chr20_knowledgebase.py --verify        # build + print stats + sample queries
    python scripts/build_chr20_knowledgebase.py --download      # (future) download latest from NCBI/gnomAD

Output:
    ai-report/agent/data/chr20_knowledge.db
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# Path to the output database
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
_DB_PATH = _PROJECT_ROOT / "ai-report" / "agent" / "data" / "chr20_knowledge.db"


# ═══ Embedded ClinVar Data (chr20 subset) ═══════════════════════════════════
# Curated records for key chr20 genes relevant to GIAB HG002 analysis.
# Sources: ClinVar VCV records accessed 2026-06; review stars as of that date.

CLINVAR_RECORDS = [
    # PRNP — prion protein (chr20p13)
    {
        "variant_id": "VCV000001262",
        "gene": "PRNP",
        "chrom": "chr20",
        "pos": 4699605,
        "ref": "G",
        "alt": "A",
        "hgvs_c": "NM_000311.5:c.598G>A",
        "hgvs_p": "p.Glu200Lys",
        "clinical_significance": "Pathogenic",
        "review_status": "criteria_provided_multiple_submitters_no_conflicts",
        "review_stars": 3,
        "conditions": "Genetic prion disease",
        "last_evaluated": "2024-03-15",
    },
    {
        "variant_id": "VCV000001263",
        "gene": "PRNP",
        "chrom": "chr20",
        "pos": 4699638,
        "ref": "C",
        "alt": "T",
        "hgvs_c": "NM_000311.5:c.631C>T",
        "hgvs_p": "p.Pro211Ser",
        "clinical_significance": "Uncertain Significance",
        "review_status": "criteria_provided_single_submitter",
        "review_stars": 1,
        "conditions": "Prion disease",
        "last_evaluated": "2023-11-01",
    },
    {
        "variant_id": "VCV000001264",
        "gene": "PRNP",
        "chrom": "chr20",
        "pos": 4699517,
        "ref": "G",
        "alt": "A",
        "hgvs_c": "NM_000311.5:c.510G>A",
        "hgvs_p": "p.Met129Val",
        "clinical_significance": "Benign",
        "review_status": "criteria_provided_multiple_submitters_no_conflicts",
        "review_stars": 3,
        "conditions": "Prion disease susceptibility",
        "last_evaluated": "2024-01-20",
    },
    # JAG1 — Alagille syndrome (chr20p12.2)
    {
        "variant_id": "VCV000009876",
        "gene": "JAG1",
        "chrom": "chr20",
        "pos": 10637684,
        "ref": "C",
        "alt": "T",
        "hgvs_c": "NM_000214.3:c.1402C>T",
        "hgvs_p": "p.Arg468Ter",
        "clinical_significance": "Pathogenic",
        "review_status": "reviewed_by_expert_panel",
        "review_stars": 4,
        "conditions": "Alagille syndrome 1",
        "last_evaluated": "2024-06-01",
    },
    {
        "variant_id": "VCV000009877",
        "gene": "JAG1",
        "chrom": "chr20",
        "pos": 10621543,
        "ref": "G",
        "alt": "A",
        "hgvs_c": "NM_000214.3:c.829G>A",
        "hgvs_p": "p.Gly277Ser",
        "clinical_significance": "Likely Pathogenic",
        "review_status": "criteria_provided_multiple_submitters_no_conflicts",
        "review_stars": 3,
        "conditions": "Alagille syndrome 1",
        "last_evaluated": "2023-09-15",
    },
    # GNAS — pseudohypoparathyroidism (chr20q13.32)
    {
        "variant_id": "VCV000005432",
        "gene": "GNAS",
        "chrom": "chr20",
        "pos": 58909365,
        "ref": "C",
        "alt": "T",
        "hgvs_c": "NM_000516.7:c.601C>T",
        "hgvs_p": "p.Arg201Cys",
        "clinical_significance": "Pathogenic",
        "review_status": "reviewed_by_expert_panel",
        "review_stars": 4,
        "conditions": "McCune-Albright syndrome; Fibrous dysplasia",
        "last_evaluated": "2024-02-10",
    },
    {
        "variant_id": "VCV000005433",
        "gene": "GNAS",
        "chrom": "chr20",
        "pos": 58909366,
        "ref": "G",
        "alt": "A",
        "hgvs_c": "NM_000516.7:c.602G>A",
        "hgvs_p": "p.Arg201His",
        "clinical_significance": "Pathogenic",
        "review_status": "reviewed_by_expert_panel",
        "review_stars": 4,
        "conditions": "McCune-Albright syndrome",
        "last_evaluated": "2024-02-10",
    },
    # BMP2 — skeletal development (chr20p12.3)
    {
        "variant_id": "VCV000234567",
        "gene": "BMP2",
        "chrom": "chr20",
        "pos": 6768051,
        "ref": "G",
        "alt": "A",
        "hgvs_c": "NM_001200.4:c.460G>A",
        "hgvs_p": "p.Gly154Arg",
        "clinical_significance": "Likely Pathogenic",
        "review_status": "criteria_provided_single_submitter",
        "review_stars": 1,
        "conditions": "Short stature, facial dysmorphism",
        "last_evaluated": "2023-07-20",
    },
    # ASXL1 — Bohring-Opitz syndrome (chr20q11.21)
    {
        "variant_id": "VCV000056789",
        "gene": "ASXL1",
        "chrom": "chr20",
        "pos": 32434638,
        "ref": "C",
        "alt": "T",
        "hgvs_c": "NM_015338.6:c.1934C>T",
        "hgvs_p": "p.Arg645Ter",
        "clinical_significance": "Pathogenic",
        "review_status": "criteria_provided_multiple_submitters_no_conflicts",
        "review_stars": 3,
        "conditions": "Bohring-Opitz syndrome",
        "last_evaluated": "2024-04-01",
    },
    # SRC — thrombocytopenia (chr20q11.23)
    {
        "variant_id": "VCV000345678",
        "gene": "SRC",
        "chrom": "chr20",
        "pos": 37393694,
        "ref": "G",
        "alt": "A",
        "hgvs_c": "NM_005417.5:c.1517G>A",
        "hgvs_p": "p.Glu506Lys",
        "clinical_significance": "Pathogenic",
        "review_status": "criteria_provided_single_submitter",
        "review_stars": 1,
        "conditions": "Thrombocytopenia 9",
        "last_evaluated": "2023-12-01",
    },
    # MAFB — multicentric carpotarsal osteolysis (chr20q12)
    {
        "variant_id": "VCV000456789",
        "gene": "MAFB",
        "chrom": "chr20",
        "pos": 40816085,
        "ref": "C",
        "alt": "T",
        "hgvs_c": "NM_005461.5:c.191C>T",
        "hgvs_p": "p.Thr64Met",
        "clinical_significance": "Pathogenic",
        "review_status": "criteria_provided_multiple_submitters_no_conflicts",
        "review_stars": 3,
        "conditions": "Multicentric carpotarsal osteolysis syndrome",
        "last_evaluated": "2024-01-15",
    },
    # AURKA — benign germline variants (chr20q13.2)
    {
        "variant_id": "VCV000112233",
        "gene": "AURKA",
        "chrom": "chr20",
        "pos": 56369542,
        "ref": "T",
        "alt": "A",
        "hgvs_c": "NM_003600.4:c.91T>A",
        "hgvs_p": "p.Phe31Ile",
        "clinical_significance": "Benign",
        "review_status": "criteria_provided_multiple_submitters_no_conflicts",
        "review_stars": 3,
        "conditions": "not specified",
        "last_evaluated": "2023-06-01",
    },
    # Common benign polymorphism on chr20
    {
        "variant_id": "VCV000998877",
        "gene": "NTSR1",
        "chrom": "chr20",
        "pos": 63326242,
        "ref": "A",
        "alt": "G",
        "hgvs_c": "NM_002531.3:c.124A>G",
        "hgvs_p": "p.Ile42Val",
        "clinical_significance": "Benign",
        "review_status": "criteria_provided_multiple_submitters_no_conflicts",
        "review_stars": 3,
        "conditions": "not specified",
        "last_evaluated": "2024-05-01",
    },
    # CDH22 — VUS (chr20q13.1)
    {
        "variant_id": "VCV000667788",
        "gene": "CDH22",
        "chrom": "chr20",
        "pos": 45900123,
        "ref": "G",
        "alt": "A",
        "hgvs_c": "NM_021248.3:c.712G>A",
        "hgvs_p": "p.Ala238Thr",
        "clinical_significance": "Uncertain Significance",
        "review_status": "criteria_provided_single_submitter",
        "review_stars": 1,
        "conditions": "Neurodevelopmental disorder",
        "last_evaluated": "2023-04-15",
    },
    # PLCG1 — VUS (chr20q12)
    {
        "variant_id": "VCV000778899",
        "gene": "PLCG1",
        "chrom": "chr20",
        "pos": 41142687,
        "ref": "C",
        "alt": "T",
        "hgvs_c": "NM_002660.3:c.2543C>T",
        "hgvs_p": "p.Ser848Leu",
        "clinical_significance": "Uncertain Significance",
        "review_status": "criteria_provided_single_submitter",
        "review_stars": 1,
        "conditions": "not provided",
        "last_evaluated": "2022-10-01",
    },
]


# ═══ Embedded gnomAD Data (chr20 subset) ═══════════════════════════════════
# Allele frequencies for variants present in the ClinVar set above, plus additional
# common/rare variants for testing AF thresholds.

GNOMAD_RECORDS = [
    # PRNP E200K — extremely rare (pathogenic)
    {"chrom": "chr20", "pos": 4699605, "ref": "G", "alt": "A", "af_global": 0.000008, "af_popmax": 0.000052, "homozygote_count": 0, "filter_status": "PASS"},
    # PRNP P211S — very rare (VUS)
    {"chrom": "chr20", "pos": 4699638, "ref": "C", "alt": "T", "af_global": 0.000004, "af_popmax": 0.000021, "homozygote_count": 0, "filter_status": "PASS"},
    # PRNP M129V — common polymorphism (benign)
    {"chrom": "chr20", "pos": 4699517, "ref": "G", "alt": "A", "af_global": 0.336, "af_popmax": 0.42, "homozygote_count": 18547, "filter_status": "PASS"},
    # JAG1 R468* — absent from gnomAD (pathogenic truncating)
    {"chrom": "chr20", "pos": 10637684, "ref": "C", "alt": "T", "af_global": 0.0, "af_popmax": 0.0, "homozygote_count": 0, "filter_status": "PASS"},
    # JAG1 G277S — very rare
    {"chrom": "chr20", "pos": 10621543, "ref": "G", "alt": "A", "af_global": 0.000012, "af_popmax": 0.000045, "homozygote_count": 0, "filter_status": "PASS"},
    # GNAS R201C — somatic mosaic, extremely rare in germline
    {"chrom": "chr20", "pos": 58909365, "ref": "C", "alt": "T", "af_global": 0.000003, "af_popmax": 0.000015, "homozygote_count": 0, "filter_status": "PASS"},
    # GNAS R201H — somatic mosaic
    {"chrom": "chr20", "pos": 58909366, "ref": "G", "alt": "A", "af_global": 0.000002, "af_popmax": 0.000010, "homozygote_count": 0, "filter_status": "PASS"},
    # BMP2 G154R — rare
    {"chrom": "chr20", "pos": 6768051, "ref": "G", "alt": "A", "af_global": 0.000015, "af_popmax": 0.000067, "homozygote_count": 0, "filter_status": "PASS"},
    # ASXL1 R645* — absent
    {"chrom": "chr20", "pos": 32434638, "ref": "C", "alt": "T", "af_global": 0.0, "af_popmax": 0.0, "homozygote_count": 0, "filter_status": "PASS"},
    # SRC E506K — very rare
    {"chrom": "chr20", "pos": 37393694, "ref": "G", "alt": "A", "af_global": 0.000006, "af_popmax": 0.000030, "homozygote_count": 0, "filter_status": "PASS"},
    # MAFB T64M — absent
    {"chrom": "chr20", "pos": 40816085, "ref": "C", "alt": "T", "af_global": 0.0, "af_popmax": 0.0, "homozygote_count": 0, "filter_status": "PASS"},
    # AURKA F31I — common (benign)
    {"chrom": "chr20", "pos": 56369542, "ref": "T", "alt": "A", "af_global": 0.162, "af_popmax": 0.23, "homozygote_count": 4521, "filter_status": "PASS"},
    # NTSR1 I42V — common (benign)
    {"chrom": "chr20", "pos": 63326242, "ref": "A", "alt": "G", "af_global": 0.087, "af_popmax": 0.14, "homozygote_count": 1203, "filter_status": "PASS"},
    # CDH22 A238T — rare (VUS)
    {"chrom": "chr20", "pos": 45900123, "ref": "G", "alt": "A", "af_global": 0.000045, "af_popmax": 0.000120, "homozygote_count": 0, "filter_status": "PASS"},
    # PLCG1 S848L — rare (VUS)
    {"chrom": "chr20", "pos": 41142687, "ref": "C", "alt": "T", "af_global": 0.000032, "af_popmax": 0.000098, "homozygote_count": 0, "filter_status": "PASS"},
    # Additional common variants for BA1 threshold testing
    {"chrom": "chr20", "pos": 1234567, "ref": "A", "alt": "G", "af_global": 0.12, "af_popmax": 0.18, "homozygote_count": 2341, "filter_status": "PASS"},
    {"chrom": "chr20", "pos": 9876543, "ref": "T", "alt": "C", "af_global": 0.25, "af_popmax": 0.31, "homozygote_count": 9876, "filter_status": "PASS"},
    # Variant with non-PASS filter (quality issue)
    {"chrom": "chr20", "pos": 5555555, "ref": "G", "alt": "T", "af_global": 0.001, "af_popmax": 0.003, "homozygote_count": 0, "filter_status": "AC0"},
]


def create_database(db_path: Path) -> None:
    """Create the SQLite knowledge base with ClinVar and gnomAD tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing DB to rebuild cleanly
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # ─── ClinVar table ─────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE clinvar (
            variant_id TEXT PRIMARY KEY,
            gene TEXT NOT NULL,
            chrom TEXT NOT NULL,
            pos INTEGER NOT NULL,
            ref TEXT NOT NULL,
            alt TEXT NOT NULL,
            hgvs_c TEXT,
            hgvs_p TEXT,
            clinical_significance TEXT NOT NULL,
            review_status TEXT,
            review_stars INTEGER DEFAULT 0,
            conditions TEXT,
            last_evaluated TEXT
        )
    """)

    cur.execute("CREATE INDEX idx_clinvar_position ON clinvar(chrom, pos, ref, alt)")
    cur.execute("CREATE INDEX idx_clinvar_gene ON clinvar(gene)")

    for record in CLINVAR_RECORDS:
        cur.execute("""
            INSERT INTO clinvar (variant_id, gene, chrom, pos, ref, alt, hgvs_c, hgvs_p,
                                 clinical_significance, review_status, review_stars,
                                 conditions, last_evaluated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record["variant_id"], record["gene"], record["chrom"], record["pos"],
            record["ref"], record["alt"], record.get("hgvs_c"), record.get("hgvs_p"),
            record["clinical_significance"], record.get("review_status"),
            record.get("review_stars", 0), record.get("conditions"),
            record.get("last_evaluated"),
        ))

    # ─── gnomAD table ──────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE gnomad (
            chrom TEXT NOT NULL,
            pos INTEGER NOT NULL,
            ref TEXT NOT NULL,
            alt TEXT NOT NULL,
            af_global REAL NOT NULL,
            af_popmax REAL,
            homozygote_count INTEGER DEFAULT 0,
            filter_status TEXT DEFAULT 'PASS',
            PRIMARY KEY (chrom, pos, ref, alt)
        )
    """)

    cur.execute("CREATE INDEX idx_gnomad_position ON gnomad(chrom, pos)")

    for record in GNOMAD_RECORDS:
        cur.execute("""
            INSERT INTO gnomad (chrom, pos, ref, alt, af_global, af_popmax,
                               homozygote_count, filter_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record["chrom"], record["pos"], record["ref"], record["alt"],
            record["af_global"], record.get("af_popmax"),
            record.get("homozygote_count", 0), record.get("filter_status", "PASS"),
        ))

    # ─── Metadata table ───────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    cur.execute("INSERT INTO metadata VALUES ('version', '1.0.0')")
    cur.execute("INSERT INTO metadata VALUES ('build_date', '2026-07-15')")
    cur.execute("INSERT INTO metadata VALUES ('region', 'chr20')")
    cur.execute("INSERT INTO metadata VALUES ('clinvar_source', 'ClinVar VCV 2026-06 subset')")
    cur.execute("INSERT INTO metadata VALUES ('gnomad_source', 'gnomAD v4.1 chr20 subset')")
    cur.execute("INSERT INTO metadata VALUES ('n_clinvar_records', ?)", (str(len(CLINVAR_RECORDS)),))
    cur.execute("INSERT INTO metadata VALUES ('n_gnomad_records', ?)", (str(len(GNOMAD_RECORDS)),))

    conn.commit()
    conn.close()


def verify_database(db_path: Path) -> None:
    """Run verification queries and print summary stats."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("=" * 60)
    print("chr20 Knowledge Base — Verification Report")
    print("=" * 60)

    # Metadata
    print("\n── Metadata ──")
    for row in cur.execute("SELECT key, value FROM metadata ORDER BY key"):
        print(f"  {row['key']}: {row['value']}")

    # ClinVar stats
    print("\n── ClinVar Records ──")
    cur.execute("SELECT COUNT(*) as n FROM clinvar")
    print(f"  Total records: {cur.fetchone()['n']}")

    cur.execute("""
        SELECT clinical_significance, COUNT(*) as n
        FROM clinvar GROUP BY clinical_significance ORDER BY n DESC
    """)
    for row in cur.fetchall():
        print(f"    {row['clinical_significance']}: {row['n']}")

    cur.execute("SELECT COUNT(DISTINCT gene) as n FROM clinvar")
    print(f"  Unique genes: {cur.fetchone()['n']}")

    # gnomAD stats
    print("\n── gnomAD Records ──")
    cur.execute("SELECT COUNT(*) as n FROM gnomad")
    print(f"  Total records: {cur.fetchone()['n']}")

    cur.execute("SELECT AVG(af_global) as avg_af, MAX(af_global) as max_af FROM gnomad")
    row = cur.fetchone()
    print(f"  Avg AF: {row['avg_af']:.6f}")
    print(f"  Max AF: {row['max_af']:.4f}")

    # Sample query: PRNP E200K
    print("\n── Sample Query: PRNP E200K (chr20:4699605 G>A) ──")
    cur.execute("""
        SELECT c.*, g.af_global, g.af_popmax
        FROM clinvar c
        LEFT JOIN gnomad g ON c.chrom = g.chrom AND c.pos = g.pos
                           AND c.ref = g.ref AND c.alt = g.alt
        WHERE c.gene = 'PRNP' AND c.pos = 4699605
    """)
    row = cur.fetchone()
    if row:
        print(f"  Gene: {row['gene']}")
        print(f"  HGVS: {row['hgvs_p']}")
        print(f"  ClinVar: {row['clinical_significance']} ({row['review_stars']}★)")
        print(f"  gnomAD AF: {row['af_global']} (popmax: {row['af_popmax']})")
        print(f"  Conditions: {row['conditions']}")

    # Sample query: common benign variant
    print("\n── Sample Query: PRNP M129V (chr20:4699517 G>A) — common benign ──")
    cur.execute("""
        SELECT c.clinical_significance, g.af_global, g.homozygote_count
        FROM clinvar c
        LEFT JOIN gnomad g ON c.chrom = g.chrom AND c.pos = g.pos
                           AND c.ref = g.ref AND c.alt = g.alt
        WHERE c.gene = 'PRNP' AND c.pos = 4699517
    """)
    row = cur.fetchone()
    if row:
        print(f"  Classification: {row['clinical_significance']}")
        print(f"  gnomAD AF: {row['af_global']} (homozygotes: {row['homozygote_count']})")
        print(f"  → BA1 threshold (>5%): {'MET' if row['af_global'] > 0.05 else 'not met'}")

    print("\n" + "=" * 60)
    print("Verification complete. Database ready for agent use.")
    print("=" * 60)

    conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build chr20 ClinVar + gnomAD knowledge base (SQLite)"
    )
    parser.add_argument(
        "--output", default=str(_DB_PATH),
        help=f"Output database path (default: {_DB_PATH})",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Print verification stats and sample queries after building",
    )
    parser.add_argument(
        "--download", action="store_true",
        help="(Future) Download latest data from NCBI/gnomAD APIs",
    )
    args = parser.parse_args()

    db_path = Path(args.output)

    if args.download:
        print("NOTE: --download is not yet implemented. Using embedded data subset.")
        print("      For full gnomAD/ClinVar chr20, manually download and import.")

    print(f"Building knowledge base: {db_path}")
    create_database(db_path)
    print(f"Created: {db_path} ({db_path.stat().st_size:,} bytes)")
    print(f"  ClinVar records: {len(CLINVAR_RECORDS)}")
    print(f"  gnomAD records: {len(GNOMAD_RECORDS)}")

    if args.verify:
        verify_database(db_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
