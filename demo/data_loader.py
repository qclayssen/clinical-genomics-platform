"""Data loading layer for the demo app.

Provides a flat DataFrame from either:
  1. The seed SQL values (parsed into Python dicts — no Postgres needed)
  2. Any metrics.json fixtures found under tests/fixtures/

This means the demo is fully self-contained: no database, no pipeline run required.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

# ── Embedded seed data (mirrors db/seed_demo.sql) ─────────────────────────────
# Keeps the demo zero-dependency on Postgres while matching the dashboard exactly.

_SEED_RUNS: list[dict] = [
    {
        "run_id": "run_2026_0301_a",
        "sample_id": "HG002_chr20",
        "pipeline_version": "0.2.0",
        "caller": "gatk",
        "started_at": datetime(2026, 3, 1, 9, 0),
        "exported_at": datetime(2026, 3, 1, 10, 12),
        "snp_precision": 0.9981,
        "snp_recall": 0.9964,
        "percent_duplication": 0.061,
        "n_variants": 61234,
    },
    {
        "run_id": "run_2026_0305_b",
        "sample_id": "HG003_chr20",
        "pipeline_version": "0.2.0",
        "caller": "gatk",
        "started_at": datetime(2026, 3, 5, 8, 40),
        "exported_at": datetime(2026, 3, 5, 9, 55),
        "snp_precision": 0.9975,
        "snp_recall": 0.9958,
        "percent_duplication": 0.072,
        "n_variants": 60112,
    },
    {
        "run_id": "run_2026_0312_c",
        "sample_id": "HG004_chr20",
        "pipeline_version": "0.2.0",
        "caller": "gatk",
        "started_at": datetime(2026, 3, 12, 11, 5),
        "exported_at": datetime(2026, 3, 12, 12, 30),
        "snp_precision": 0.9962,
        "snp_recall": 0.9901,
        "percent_duplication": 0.089,
        "n_variants": 59880,
    },
    {
        "run_id": "run_2026_0401_d",
        "sample_id": "HG002_chr20",
        "pipeline_version": "0.3.0",
        "caller": "deepvariant",
        "started_at": datetime(2026, 4, 1, 9, 15),
        "exported_at": datetime(2026, 4, 1, 10, 5),
        "snp_precision": 0.9994,
        "snp_recall": 0.9989,
        "percent_duplication": 0.058,
        "n_variants": 62010,
    },
    {
        "run_id": "run_2026_0405_e",
        "sample_id": "NA12878_chr20",
        "pipeline_version": "0.3.0",
        "caller": "deepvariant",
        "started_at": datetime(2026, 4, 5, 14, 20),
        "exported_at": datetime(2026, 4, 5, 15, 2),
        "snp_precision": 0.9990,
        "snp_recall": 0.9980,
        "percent_duplication": 0.064,
        "n_variants": 61540,
    },
    {
        "run_id": "run_2026_0409_f",
        "sample_id": "HG003_chr20",
        "pipeline_version": "0.3.0",
        "caller": "deepvariant",
        "started_at": datetime(2026, 4, 9, 10, 0),
        "exported_at": datetime(2026, 4, 9, 10, 44),
        "snp_precision": 0.9987,
        "snp_recall": 0.9975,
        "percent_duplication": 0.070,
        "n_variants": 60890,
    },
]


def _compute_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Add computed columns that mirror the v_run_summary view."""
    # SNP F1 = harmonic mean of precision and recall
    df["snp_f1"] = (
        2 * df["snp_precision"] * df["snp_recall"]
        / (df["snp_precision"] + df["snp_recall"])
    )
    # Validation pass: F1 >= 0.99
    df["validation_pass"] = df["snp_f1"] >= 0.99
    # Turnaround in minutes
    df["turnaround_min"] = (
        (df["exported_at"] - df["started_at"]).dt.total_seconds() / 60.0
    )
    return df


def load_seed_data() -> pd.DataFrame:
    """Load the embedded seed data as a DataFrame (no external deps)."""
    df = pd.DataFrame(_SEED_RUNS)
    df["started_at"] = pd.to_datetime(df["started_at"])
    df["exported_at"] = pd.to_datetime(df["exported_at"])
    return _compute_derived(df)


def load_metrics_fixtures(fixtures_dir: Path | None = None) -> pd.DataFrame:
    """Load any metrics.json files from the test fixtures directory.

    Returns an empty DataFrame if the directory doesn't exist or has no files.
    """
    if fixtures_dir is None:
        fixtures_dir = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

    if not fixtures_dir.exists():
        return pd.DataFrame()

    import json

    rows: list[dict] = []
    for path in sorted(fixtures_dir.glob("*.metrics.json")):
        with open(path) as fh:
            m = json.load(fh)
        prov = m.get("provenance", {})
        snp = m.get("validation", {}).get("snp", {})
        rows.append(
            {
                "run_id": prov.get("run_id", path.stem),
                "sample_id": m.get("sample", path.stem),
                "pipeline_version": prov.get("pipeline_version", "unknown"),
                "caller": prov.get("caller", "unknown"),
                "started_at": pd.to_datetime(prov.get("started_at")),
                "exported_at": pd.to_datetime(prov.get("exported_at")),
                "snp_precision": snp.get("precision"),
                "snp_recall": snp.get("recall"),
                "percent_duplication": m.get("qc", {}).get("percent_duplication"),
                "n_variants": prov.get("n_variants"),
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return _compute_derived(df)


def load_all_data() -> pd.DataFrame:
    """Load seed data + any fixture metrics, deduplicated by run_id."""
    seed = load_seed_data()
    fixtures = load_metrics_fixtures()

    if fixtures.empty:
        return seed

    combined = pd.concat([seed, fixtures], ignore_index=True)
    combined = combined.drop_duplicates(subset=["run_id"], keep="first")
    return combined.sort_values("started_at").reset_index(drop=True)


def get_summary_stats(df: pd.DataFrame) -> dict:
    """Compute headline statistics for the KPI cards."""
    return {
        "total_runs": len(df),
        "pass_rate_pct": round(100.0 * df["validation_pass"].mean(), 1),
        "mean_snp_f1": round(df["snp_f1"].mean(), 4),
        "mean_turnaround_min": round(df["turnaround_min"].mean(), 1),
        "samples": sorted(df["sample_id"].unique().tolist()),
        "callers": sorted(df["caller"].unique().tolist()),
        "versions": sorted(df["pipeline_version"].unique().tolist()),
    }
