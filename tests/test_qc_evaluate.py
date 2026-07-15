"""Tests for qc_evaluate.py — QC metric evaluation script.

Validates:
- parse_fastp_json extracts q30_rate and reads_filtered_percent
- parse_dup_metrics extracts percent_duplication
- parse_happy_summary extracts snp_f1, snp_precision, snp_recall
- evaluate_metrics produces correct pass/warn/fail per metric
- Overall status escalation (pass → warn → fail)
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Ensure pipeline/bin is in sys.path for imports
bin_dir = str(ROOT / "pipeline" / "bin")
if bin_dir not in sys.path:
    sys.path.insert(0, bin_dir)


def _load(module_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


qc_evaluate = _load(ROOT / "pipeline" / "bin" / "qc_evaluate.py", "qc_evaluate")

parse_fastp_json = qc_evaluate.parse_fastp_json
parse_dup_metrics = qc_evaluate.parse_dup_metrics
parse_happy_summary = qc_evaluate.parse_happy_summary
evaluate_metrics = qc_evaluate.evaluate_metrics


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def fastp_json(tmp_path):
    """Create a minimal fastp JSON output."""
    data = {
        "summary": {
            "before_filtering": {
                "total_reads": 1000000,
                "q30_rate": 0.88,
            },
            "after_filtering": {
                "total_reads": 950000,
                "q30_rate": 0.92,
            },
        },
        "filtering_result": {
            "passed_filter_reads": 950000,
            "low_quality_reads": 30000,
            "too_many_N_reads": 5000,
            "too_short_reads": 15000,
            "too_long_reads": 0,
        },
    }
    path = tmp_path / "sample.fastp.json"
    path.write_text(json.dumps(data))
    return path


@pytest.fixture
def dup_metrics(tmp_path):
    """Create a minimal MarkDuplicates metrics file."""
    content = (
        "## htsjdk.samtools.metrics.StringHeader\n"
        "# MarkDuplicates example\n"
        "## METRICS CLASS\tpicard.sam.DuplicationMetrics\n"
        "LIBRARY\tPERCENT_DUPLICATION\tESTIMATED_LIBRARY_SIZE\n"
        "HG002_chr20\t0.061\t9500000\n"
    )
    path = tmp_path / "sample.markdup.metrics"
    path.write_text(content)
    return path


@pytest.fixture
def happy_summary(tmp_path):
    """Create a minimal hap.py summary CSV."""
    content = (
        "Type,Filter,TRUTH.TOTAL,TRUTH.TP,TRUTH.FN,QUERY.TOTAL,QUERY.FP,"
        "METRIC.Recall,METRIC.Precision,METRIC.F1_Score\n"
        "INDEL,PASS,11200,11100,100,11250,80,0.9911,0.9929,0.9920\n"
        "SNP,PASS,71000,70794,206,71010,110,0.9971,0.9985,0.9978\n"
    )
    path = tmp_path / "sample.happy.summary.csv"
    path.write_text(content)
    return path


@pytest.fixture
def thresholds_config():
    """Return the thresholds config as a dict."""
    return {
        "metrics": {
            "percent_duplication": {
                "direction": "higher_is_worse",
                "warn": 0.20,
                "fail": 0.40,
                "unit": "fraction",
            },
            "q30_rate": {
                "direction": "lower_is_worse",
                "warn": 0.80,
                "fail": 0.70,
                "unit": "fraction",
            },
            "reads_filtered_percent": {
                "direction": "higher_is_worse",
                "warn": 0.30,
                "fail": 0.50,
                "unit": "fraction",
            },
            "snp_f1": {
                "direction": "lower_is_worse",
                "warn": 0.995,
                "fail": 0.99,
                "unit": "score",
            },
            "snp_precision": {
                "direction": "lower_is_worse",
                "warn": 0.995,
                "fail": 0.99,
                "unit": "score",
            },
            "snp_recall": {
                "direction": "lower_is_worse",
                "warn": 0.995,
                "fail": 0.99,
                "unit": "score",
            },
        }
    }


# ══════════════════════════════════════════════════════════════════════════════
# Test: parse_fastp_json
# ══════════════════════════════════════════════════════════════════════════════


class TestParseFastpJson:
    """Test fastp JSON parsing."""

    def test_extracts_q30_rate(self, fastp_json):
        """Extracts q30_rate from after_filtering."""
        result = parse_fastp_json(str(fastp_json))
        assert result["q30_rate"] == 0.92

    def test_extracts_reads_filtered_percent(self, fastp_json):
        """Computes reads_filtered_percent from filtering_result."""
        result = parse_fastp_json(str(fastp_json))
        # 50000 filtered / 1000000 total = 0.05
        assert abs(result["reads_filtered_percent"] - 0.05) < 0.001

    def test_empty_summary_returns_empty(self, tmp_path):
        """Empty fastp JSON returns empty dict."""
        path = tmp_path / "empty.json"
        path.write_text(json.dumps({"summary": {}}))
        result = parse_fastp_json(str(path))
        assert "q30_rate" not in result


# ══════════════════════════════════════════════════════════════════════════════
# Test: parse_dup_metrics
# ══════════════════════════════════════════════════════════════════════════════


class TestParseDupMetrics:
    """Test MarkDuplicates metrics parsing."""

    def test_extracts_percent_duplication(self, dup_metrics):
        """Extracts PERCENT_DUPLICATION correctly."""
        result = parse_dup_metrics(str(dup_metrics))
        assert result["percent_duplication"] == 0.061

    def test_committed_fixture(self):
        """Parses the committed test fixture."""
        path = ROOT / "tests" / "fixtures" / "sample.markdup.metrics"
        result = parse_dup_metrics(str(path))
        assert result["percent_duplication"] == 0.061

    def test_missing_value_returns_empty(self, tmp_path):
        """Missing PERCENT_DUPLICATION returns empty dict."""
        path = tmp_path / "bad.metrics"
        path.write_text("LIBRARY\tPERCENT_DUPLICATION\n")
        result = parse_dup_metrics(str(path))
        assert result == {}


# ══════════════════════════════════════════════════════════════════════════════
# Test: parse_happy_summary
# ══════════════════════════════════════════════════════════════════════════════


class TestParseHappySummary:
    """Test hap.py summary CSV parsing."""

    def test_extracts_snp_metrics(self, happy_summary):
        """Extracts SNP precision, recall, F1."""
        result = parse_happy_summary(str(happy_summary))
        assert result["snp_precision"] == 0.9985
        assert result["snp_recall"] == 0.9971
        assert result["snp_f1"] == 0.9978

    def test_committed_fixture(self):
        """Parses the committed test fixture."""
        path = ROOT / "tests" / "fixtures" / "sample.happy.summary.csv"
        result = parse_happy_summary(str(path))
        assert result["snp_f1"] == 0.9978
        assert result["snp_precision"] == 0.9985
        assert result["snp_recall"] == 0.9971

    def test_no_snp_row_returns_empty(self, tmp_path):
        """CSV without SNP row returns empty dict."""
        content = (
            "Type,METRIC.Precision,METRIC.Recall,METRIC.F1_Score\n"
            "INDEL,0.99,0.98,0.985\n"
        )
        path = tmp_path / "no_snp.csv"
        path.write_text(content)
        result = parse_happy_summary(str(path))
        assert result == {}


# ══════════════════════════════════════════════════════════════════════════════
# Test: evaluate_metrics
# ══════════════════════════════════════════════════════════════════════════════


class TestEvaluateMetrics:
    """Test metric evaluation against thresholds."""

    def test_all_pass(self, thresholds_config):
        """Good values all evaluate to pass."""
        metrics = {
            "percent_duplication": 0.05,
            "q30_rate": 0.92,
            "reads_filtered_percent": 0.05,
            "snp_f1": 0.998,
            "snp_precision": 0.998,
            "snp_recall": 0.997,
        }
        results, overall = evaluate_metrics(metrics, thresholds_config)
        assert overall == "pass"
        for name, r in results.items():
            assert r["status"] == "pass", f"{name} should be pass"

    def test_warn_escalation(self, thresholds_config):
        """One warn metric escalates overall to warn."""
        metrics = {
            "percent_duplication": 0.25,  # warn
            "q30_rate": 0.92,
            "snp_f1": 0.998,
        }
        results, overall = evaluate_metrics(metrics, thresholds_config)
        assert overall == "warn"
        assert results["percent_duplication"]["status"] == "warn"

    def test_fail_escalation(self, thresholds_config):
        """One fail metric escalates overall to fail (even if others pass/warn)."""
        metrics = {
            "percent_duplication": 0.25,  # warn
            "q30_rate": 0.60,  # fail
            "snp_f1": 0.998,  # pass
        }
        results, overall = evaluate_metrics(metrics, thresholds_config)
        assert overall == "fail"
        assert results["q30_rate"]["status"] == "fail"

    def test_unknown_metrics_skipped(self, thresholds_config):
        """Metrics not in config are silently skipped."""
        metrics = {
            "percent_duplication": 0.05,
            "unknown_thing": 999.0,
        }
        results, overall = evaluate_metrics(metrics, thresholds_config)
        assert "unknown_thing" not in results
        assert "percent_duplication" in results

    def test_lower_is_worse_boundaries(self, thresholds_config):
        """Test boundary conditions for lower_is_worse metrics."""
        # At boundary: exactly at warn → pass (not < warn)
        metrics_at_warn = {"snp_f1": 0.995}
        results, _ = evaluate_metrics(metrics_at_warn, thresholds_config)
        assert results["snp_f1"]["status"] == "pass"

        # Below warn → warn
        metrics_below_warn = {"snp_f1": 0.994}
        results, _ = evaluate_metrics(metrics_below_warn, thresholds_config)
        assert results["snp_f1"]["status"] == "warn"

        # At fail → warn (not < fail)
        metrics_at_fail = {"snp_f1": 0.99}
        results, _ = evaluate_metrics(metrics_at_fail, thresholds_config)
        assert results["snp_f1"]["status"] == "warn"

        # Below fail → fail
        metrics_below_fail = {"snp_f1": 0.989}
        results, _ = evaluate_metrics(metrics_below_fail, thresholds_config)
        assert results["snp_f1"]["status"] == "fail"

    def test_result_includes_threshold_info(self, thresholds_config):
        """Results include threshold values and direction."""
        metrics = {"percent_duplication": 0.05}
        results, _ = evaluate_metrics(metrics, thresholds_config)
        r = results["percent_duplication"]
        assert r["warn_threshold"] == 0.20
        assert r["fail_threshold"] == 0.40
        assert r["direction"] == "higher_is_worse"
        assert r["value"] == 0.05


# ══════════════════════════════════════════════════════════════════════════════
# Integration test: full evaluation with all parsers
# ══════════════════════════════════════════════════════════════════════════════


class TestFullEvaluation:
    """End-to-end test combining parsing + evaluation."""

    def test_all_inputs_combined(self, fastp_json, dup_metrics, happy_summary, thresholds_config):
        """All parsers feed into evaluation correctly."""
        metrics = {}
        metrics.update(parse_fastp_json(str(fastp_json)))
        metrics.update(parse_dup_metrics(str(dup_metrics)))
        metrics.update(parse_happy_summary(str(happy_summary)))

        results, overall = evaluate_metrics(metrics, thresholds_config)

        # All our test fixtures have good values
        assert overall in ("pass", "warn")
        assert "percent_duplication" in results
        assert "q30_rate" in results
        assert "snp_f1" in results
        assert "snp_precision" in results
        assert "snp_recall" in results

    def test_committed_fixtures_produce_pass(self, thresholds_config):
        """Committed fixtures: all metrics within thresholds → overall pass."""
        fx = ROOT / "tests" / "fixtures"
        metrics = {}
        metrics.update(parse_dup_metrics(str(fx / "sample.markdup.metrics")))
        metrics.update(parse_happy_summary(str(fx / "sample.happy.summary.csv")))

        results, overall = evaluate_metrics(metrics, thresholds_config)

        # The committed fixture has:
        # percent_duplication=0.061 (<0.20 → pass)
        # snp_f1=0.9978 (>0.995 → pass)
        # snp_precision=0.9985 (>0.995 → pass)
        # snp_recall=0.9971 (>0.995 → pass)
        assert results["percent_duplication"]["status"] == "pass"
        assert results["snp_f1"]["status"] == "pass"
        assert results["snp_precision"]["status"] == "pass"
        assert results["snp_recall"]["status"] == "pass"
        assert overall == "pass"
