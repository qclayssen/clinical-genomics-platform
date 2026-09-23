"""Unit tests for the dependency-free pipeline helpers.

These run in CI without Nextflow, Docker, or any bioinformatics tool installed —
they exercise the provenance/traceability logic that the whole platform's
credibility rests on.
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# infer.py imports the shared `guardrails` module as a bare top-level module
# (ai-report/ isn't a package root — see api/routers/agent.py for the same
# pattern), so ai-report/ must be on sys.path before infer.py is exec'd below.
_AI_REPORT_DIR = ROOT / "ai-report"
if str(_AI_REPORT_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_REPORT_DIR))


def _load(module_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bm = _load(ROOT / "pipeline" / "bin" / "build_metrics.py", "build_metrics")
infer = _load(ROOT / "ai-report" / "infer.py", "infer")
guardrails = _load(_AI_REPORT_DIR / "guardrails.py", "guardrails")


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


def test_main_checksums_reference_and_truth_set_inputs(tmp_path, monkeypatch):
    """--inputs must cover the reference/truth set, not just the two derived
    artifacts — closing the gap tracked in docs/FIXES-TODO.md so a result is
    cryptographically bound to what it was benchmarked against."""
    dup = tmp_path / "dup.metrics"
    dup.write_text("LIBRARY\tPERCENT_DUPLICATION\ns\t0.05\n")
    happy = tmp_path / "happy.csv"
    happy.write_text(
        "Type,METRIC.Precision,METRIC.Recall,METRIC.F1_Score\nSNP,0.995,0.994,0.9945\n"
    )
    reference = tmp_path / "ref.fasta"
    reference.write_text(">chr20\nACGT\n")
    truth_vcf = tmp_path / "truth.vcf"
    truth_vcf.write_text("##fileformat=VCFv4.2\n")
    truth_bed = tmp_path / "truth.bed"
    truth_bed.write_text("chr20\t0\t100\n")
    output = tmp_path / "out.metrics.json"

    argv = [
        "build_metrics.py",
        "--sample", "HG002_chr20",
        "--dup-metrics", str(dup),
        "--happy-summary", str(happy),
        "--provenance", json.dumps({"git_commit": "abc1234", "truth_version": "GIAB-v4.2.1"}),
        "--inputs", f"{dup},{happy},{reference},{truth_vcf},{truth_bed}",
        "--output", str(output),
    ]
    monkeypatch.setattr("sys.argv", argv)
    assert bm.main() == 0

    record = json.loads(output.read_text())
    checksums = record["provenance"]["input_checksums"]
    assert set(checksums) == {
        "dup.metrics", "happy.csv", "ref.fasta", "truth.vcf", "truth.bed",
    }
    assert checksums["ref.fasta"] == bm.sha256(str(reference))
    assert checksums["truth.vcf"] == bm.sha256(str(truth_vcf))
    assert checksums["truth.bed"] == bm.sha256(str(truth_bed))


def test_parse_tool_versions_reads_nfcore_versions_yml(tmp_path):
    """The caller's own versions.yml (nf-core shape) is the source of caller_version."""
    versions = tmp_path / "caller_versions.yml"
    versions.write_text('"HAPLOTYPECALLER":\n    gatk4: 4.5.0.0\n')
    assert bm.parse_tool_versions(str(versions)) == {"gatk4": "4.5.0.0"}


def test_parse_tool_versions_empty_file_yields_empty_map(tmp_path):
    versions = tmp_path / "caller_versions.yml"
    versions.write_text("")
    assert bm.parse_tool_versions(str(versions)) == {}


def test_main_stamps_caller_version_and_checksums_reads(tmp_path, monkeypatch):
    """Closes two provenance gaps from docs/FIXES-TODO.md: the stamp names the caller
    version the caller itself reported, and the raw FASTQ reads are checksummed."""
    dup = tmp_path / "dup.metrics"
    dup.write_text("LIBRARY\tPERCENT_DUPLICATION\ns\t0.05\n")
    happy = tmp_path / "happy.csv"
    happy.write_text(
        "Type,METRIC.Precision,METRIC.Recall,METRIC.F1_Score\nSNP,0.995,0.994,0.9945\n"
    )
    r1 = tmp_path / "S_R1.fastq.gz"
    r1.write_bytes(b"read-one")
    r2 = tmp_path / "S_R2.fastq.gz"
    r2.write_bytes(b"read-two")
    versions = tmp_path / "caller_versions.yml"
    versions.write_text('"HAPLOTYPECALLER":\n    gatk4: 4.5.0.0\n')
    output = tmp_path / "out.metrics.json"

    argv = [
        "build_metrics.py",
        "--sample", "S",
        "--dup-metrics", str(dup),
        "--happy-summary", str(happy),
        "--provenance", json.dumps({"git_commit": "abc1234"}),
        "--inputs", f"{dup},{happy},{r1},{r2}",
        "--caller-versions", str(versions),
        "--output", str(output),
    ]
    monkeypatch.setattr("sys.argv", argv)
    assert bm.main() == 0

    prov = json.loads(output.read_text())["provenance"]
    assert prov["caller_version"] == {"gatk4": "4.5.0.0"}
    assert prov["input_checksums"]["S_R1.fastq.gz"] == bm.sha256(str(r1))
    assert prov["input_checksums"]["S_R2.fastq.gz"] == bm.sha256(str(r2))


def test_guardrails_reinsert_banner_if_model_drops_it():
    metrics = {"provenance": {"git_commit": "deadbee", "truth_version": "GIAB-v4.2.1"}}
    hostile = "Sample looks great. We recommend treatment with drug X."
    fixed = infer.enforce_guardrails(hostile, metrics)
    assert fixed.startswith("AI-DRAFTED — REQUIRES CLINICIAN REVIEW")
    assert "recommend" not in fixed.lower()   # scrubbed
    assert "Provenance:" in fixed
