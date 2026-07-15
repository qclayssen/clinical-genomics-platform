"""Tests for MultiQC configuration with conditional formatting rules.

Validates:
- Generated YAML is valid and parseable
- Contains expected formatting rules for all QC metrics
- Colors are defined for pass/warn/fail
- Report header info is present
"""
from pathlib import Path

import yaml
import pytest

ROOT = Path(__file__).resolve().parents[1]
MULTIQC_CONFIG = ROOT / "pipeline" / "assets" / "multiqc_config.yaml"


@pytest.fixture
def config():
    """Load the MultiQC config."""
    with open(MULTIQC_CONFIG) as fh:
        return yaml.safe_load(fh)


class TestMultiqcConfigValid:
    """Test that the MultiQC config is valid YAML with required structure."""

    def test_file_exists(self):
        """Config file exists at expected path."""
        assert MULTIQC_CONFIG.exists()

    def test_valid_yaml(self):
        """Config file is valid YAML."""
        with open(MULTIQC_CONFIG) as fh:
            data = yaml.safe_load(fh)
        assert isinstance(data, dict)

    def test_has_table_cond_formatting_rules(self, config):
        """Config has table_cond_formatting_rules section."""
        assert "table_cond_formatting_rules" in config
        assert isinstance(config["table_cond_formatting_rules"], dict)

    def test_has_table_cond_formatting_colours(self, config):
        """Config has color definitions for pass/warn/fail."""
        assert "table_cond_formatting_colours" in config
        colours = config["table_cond_formatting_colours"]
        assert isinstance(colours, list)

        # Extract all defined categories
        categories = set()
        for item in colours:
            categories.update(item.keys())
        assert "pass" in categories
        assert "warn" in categories
        assert "fail" in categories

    def test_has_report_header_info(self, config):
        """Config has report_header_info with platform name."""
        assert "report_header_info" in config
        header_info = config["report_header_info"]
        assert isinstance(header_info, list)
        # Check platform name is present
        header_keys = set()
        for item in header_info:
            header_keys.update(item.keys())
        assert "Platform" in header_keys


class TestConditionalFormattingRules:
    """Test that formatting rules cover all QC metrics with correct operators."""

    def test_duplication_rate_rules(self, config):
        """Duplication rate has pass/warn/fail rules."""
        rules = config["table_cond_formatting_rules"]
        assert "PERCENT_DUPLICATION" in rules
        dup_rules = rules["PERCENT_DUPLICATION"]
        assert "pass" in dup_rules
        assert "warn" in dup_rules
        assert "fail" in dup_rules

    def test_duplication_rate_thresholds(self, config):
        """Duplication rate thresholds match qc_thresholds.yaml."""
        rules = config["table_cond_formatting_rules"]["PERCENT_DUPLICATION"]
        # pass: le 0.20
        assert any(r.get("le") == 0.20 for r in rules["pass"])
        # fail: gt 0.40
        assert any(r.get("gt") == 0.40 for r in rules["fail"])

    def test_q30_rate_rules(self, config):
        """Q30 rate has conditional formatting rules."""
        rules = config["table_cond_formatting_rules"]
        # fastp reports this under different column names
        assert "after_filtering_q30_rate" in rules or "% Q30" in rules

    def test_f1_score_rules(self, config):
        """F1 score has conditional formatting rules."""
        rules = config["table_cond_formatting_rules"]
        assert "METRIC.F1_Score" in rules
        f1_rules = rules["METRIC.F1_Score"]
        assert "pass" in f1_rules
        assert "warn" in f1_rules
        assert "fail" in f1_rules

    def test_f1_score_thresholds(self, config):
        """F1 score thresholds match qc_thresholds.yaml."""
        rules = config["table_cond_formatting_rules"]["METRIC.F1_Score"]
        # pass: ge 0.995
        assert any(r.get("ge") == 0.995 for r in rules["pass"])
        # fail: lt 0.99
        assert any(r.get("lt") == 0.99 for r in rules["fail"])

    def test_precision_rules(self, config):
        """Precision has conditional formatting rules."""
        rules = config["table_cond_formatting_rules"]
        assert "METRIC.Precision" in rules

    def test_recall_rules(self, config):
        """Recall has conditional formatting rules."""
        rules = config["table_cond_formatting_rules"]
        assert "METRIC.Recall" in rules

    def test_all_rules_use_valid_operators(self, config):
        """All formatting rules use valid MultiQC operators (gt, lt, ge, le)."""
        valid_operators = {"gt", "lt", "ge", "le"}
        rules = config["table_cond_formatting_rules"]
        for metric_name, metric_rules in rules.items():
            for status, conditions in metric_rules.items():
                assert isinstance(conditions, list), (
                    f"{metric_name}.{status}: conditions must be a list"
                )
                for condition in conditions:
                    assert isinstance(condition, dict), (
                        f"{metric_name}.{status}: each condition must be a dict"
                    )
                    for op in condition.keys():
                        assert op in valid_operators, (
                            f"{metric_name}.{status}: invalid operator '{op}'"
                        )

    def test_pass_warn_fail_all_covered(self, config):
        """Every metric has all three status levels defined."""
        rules = config["table_cond_formatting_rules"]
        for metric_name, metric_rules in rules.items():
            assert "pass" in metric_rules, f"{metric_name} missing 'pass' rule"
            assert "warn" in metric_rules, f"{metric_name} missing 'warn' rule"
            assert "fail" in metric_rules, f"{metric_name} missing 'fail' rule"
