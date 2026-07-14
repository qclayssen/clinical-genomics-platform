"""Unit tests for the dependency-free pipeline helpers.

These run in CI without Nextflow, Docker, or any bioinformatics tool installed —
they exercise the provenance/traceability logic that the whole platform's
credibility rests on.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(module_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bm = _load(ROOT / "pipeline" / "bin" / "build_metrics.py", "build_metrics")
infer = _load(ROOT / "ai-report" / "infer.py", "infer")


def test_parse_happy_extracts_snp_and_indel(tmp_path):
    csv = tmp_path / "happy.csv"
    csv.write_text(
        "Type,METRIC.Precision,METRIC.Recall,METRIC.F1_Score\n"
        "SNP,0.9985,0.9971,0.9978\nINDEL,0.9932,0.9910,0.9921\n"
    )
    out = bm.parse_happy(str(csv))
    assert out["snp"]["precision"] == 0.9985
    assert out["indel"]["f1"] == 0.9921


def test_sha256_is_stable(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("genomics")
    assert bm.sha256(str(f)) == bm.sha256(str(f))
    assert len(bm.sha256(str(f))) == 64


def test_validation_pass_threshold(tmp_path):
    dup = tmp_path / "dup.metrics"
    dup.write_text("LIBRARY\tPERCENT_DUPLICATION\ns\t0.05\n")
    happy = tmp_path / "happy.csv"
    happy.write_text(
        "Type,METRIC.Precision,METRIC.Recall,METRIC.F1_Score\nSNP,0.995,0.994,0.9945\n"
    )
    dup_parsed = bm.parse_dup_metrics(str(dup))
    happy_parsed = bm.parse_happy(str(happy))
    assert dup_parsed["percent_duplication"] == 0.05
    assert happy_parsed["snp"]["f1"] >= 0.99


def test_report_always_has_banner_and_provenance():
    metrics = {
        "sample": "HG002_chr20",
        "validation_pass": True,
        "qc": {"percent_duplication": 0.06},
        "validation": {"snp": {"precision": 0.998, "recall": 0.997, "f1": 0.9975}},
        "provenance": {"caller": "gatk", "git_commit": "abc1234",
                       "truth_version": "GIAB-v4.2.1", "n_variants": 61000},
    }
    report = infer.render_offline(metrics)
    report = infer.enforce_guardrails(report, metrics)
    assert report.startswith("AI-DRAFTED — REQUIRES CLINICIAN REVIEW")
    assert "Provenance: git abc1234" in report
    assert "validation.snp.precision" in report


def test_committed_fixtures_parse():
    """The small committed fixtures must stay valid so CI/demos work offline."""
    fx = ROOT / "tests" / "fixtures"
    happy = bm.parse_happy(str(fx / "sample.happy.summary.csv"))
    assert happy["snp"]["f1"] == 0.9978
    dup = bm.parse_dup_metrics(str(fx / "sample.markdup.metrics"))
    assert dup["percent_duplication"] == 0.061

    metrics = json.loads((fx / "HG002_chr20.metrics.json").read_text())
    report = infer.enforce_guardrails(infer.render_offline(metrics), metrics)
    assert report.startswith("AI-DRAFTED — REQUIRES CLINICIAN REVIEW")
    assert "61,234 variants" in report  # n_variants rendered from the fixture


def test_curated_training_pairs_are_wellformed():
    """Every committed training pair must have a compliant target summary."""
    path = ROOT / "ai-report" / "data" / "report_pairs.sample.jsonl"
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    assert len(lines) >= 10
    for line in lines:
        rec = json.loads(line)
        json.loads(rec["input"])  # input is valid JSON
        assert rec["output"].startswith("AI-DRAFTED — REQUIRES CLINICIAN REVIEW")
        assert "Provenance:" in rec["output"]


def test_guardrails_reinsert_banner_if_model_drops_it():
    metrics = {"provenance": {"git_commit": "deadbee", "truth_version": "GIAB-v4.2.1"}}
    hostile = "Sample looks great. We recommend treatment with drug X."
    fixed = infer.enforce_guardrails(hostile, metrics)
    assert fixed.startswith("AI-DRAFTED — REQUIRES CLINICIAN REVIEW")
    assert "recommend" not in fixed.lower()   # scrubbed
    assert "Provenance:" in fixed
