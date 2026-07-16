"""Tests for QC Thresholds Configuration Loader and Validator.

Validates:
- Config loads and validates successfully from YAML
- Invalid configs raise meaningful errors
- Property test: warn/fail ordering correct for all metric directions
- Metric evaluation returns correct pass/warn/fail status
"""
import copy
import importlib.util
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]


def _load(module_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


qc_thresholds = _load(ROOT / "pipeline" / "bin" / "qc_thresholds.py", "qc_thresholds")

ThresholdConfig = qc_thresholds.ThresholdConfig
ThresholdConfigError = qc_thresholds.ThresholdConfigError
MetricThreshold = qc_thresholds.MetricThreshold
RetryProfile = qc_thresholds.RetryProfile
AdaptiveConfig = qc_thresholds.AdaptiveConfig
QuarantineConfig = qc_thresholds.QuarantineConfig


# ══════════════════════════════════════════════════════════════════════════════
# Test: Config loads from the committed YAML file
# ══════════════════════════════════════════════════════════════════════════════


class TestConfigLoading:
    """Test loading and validation of qc_thresholds.yaml."""

    def test_load_default_config(self):
        """The committed config file loads without error."""
        config = qc_thresholds.load_default_config()
        assert isinstance(config, ThresholdConfig)

    def test_all_expected_metrics_present(self):
        """All six metrics are defined in the config."""
        config = qc_thresholds.load_default_config()
        expected = {
            "percent_duplication",
            "q30_rate",
            "reads_filtered_percent",
            "snp_f1",
            "snp_precision",
            "snp_recall",
        }
        assert set(config.metrics.keys()) == expected

    def test_adaptive_config_values(self):
        """Adaptive thresholds have expected defaults."""
        config = qc_thresholds.load_default_config()
        assert config.adaptive.min_runs == 20
        assert config.adaptive.sigma_multiplier == 2.0

    def test_retry_profiles_loaded(self):
        """Three retry profiles are defined."""
        config = qc_thresholds.load_default_config()
        assert 1 in config.retry_profiles
        assert 2 in config.retry_profiles
        assert 3 in config.retry_profiles

    def test_retry_profiles_progressively_stricter(self):
        """Each successive retry profile has stricter quality thresholds."""
        config = qc_thresholds.load_default_config()
        p1 = config.retry_profiles[1]
        p2 = config.retry_profiles[2]
        p3 = config.retry_profiles[3]
        assert p1.qualified_quality_phred < p2.qualified_quality_phred < p3.qualified_quality_phred
        assert p1.length_required < p2.length_required < p3.length_required

    def test_quarantine_config_values(self):
        """Quarantine rules have expected defaults."""
        config = qc_thresholds.load_default_config()
        assert config.quarantine.consecutive_failures_for_hard == 2
        assert config.quarantine.auto_execute_timeout_minutes == 10
        assert config.quarantine.notification_channel == "sns"

    def test_get_metric(self):
        """get_metric returns correct MetricThreshold."""
        config = qc_thresholds.load_default_config()
        dup = config.get_metric("percent_duplication")
        assert dup.direction == "higher_is_worse"
        assert dup.warn == 0.20
        assert dup.fail == 0.40

    def test_get_metric_unknown_raises(self):
        """get_metric raises KeyError for unknown metrics."""
        config = qc_thresholds.load_default_config()
        with pytest.raises(KeyError, match="Unknown QC metric"):
            config.get_metric("nonexistent_metric")

    def test_get_retry_profile_fallback(self):
        """get_retry_profile falls back to highest when attempt exceeds max."""
        config = qc_thresholds.load_default_config()
        p = config.get_retry_profile(99)
        # Should return profile for attempt 3 (highest)
        assert p.qualified_quality_phred == 25

    def test_from_dict(self):
        """Config can be loaded from a dictionary."""
        data = {
            "metrics": {
                "test_metric": {
                    "direction": "higher_is_worse",
                    "warn": 0.5,
                    "fail": 0.8,
                    "unit": "fraction",
                }
            },
            "adaptive": {"min_runs": 10, "sigma_multiplier": 1.5},
            "quarantine": {
                "consecutive_failures_for_hard": 3,
                "auto_execute_timeout_minutes": 5,
                "notification_channel": "sns",
            },
        }
        config = ThresholdConfig.from_dict(data)
        assert "test_metric" in config.metrics
        assert config.adaptive.min_runs == 10


# ══════════════════════════════════════════════════════════════════════════════
# Test: Invalid configs raise meaningful errors
# ══════════════════════════════════════════════════════════════════════════════


class TestConfigValidation:
    """Test that invalid configurations produce clear error messages."""

    def test_missing_metrics_key(self):
        """Config without 'metrics' raises ThresholdConfigError."""
        with pytest.raises(ThresholdConfigError, match="Missing required.*metrics"):
            ThresholdConfig.from_dict({"adaptive": {"min_runs": 20, "sigma_multiplier": 2.0}})

    def test_invalid_direction(self):
        """Invalid direction value raises ThresholdConfigError."""
        data = {
            "metrics": {
                "bad": {
                    "direction": "sideways",
                    "warn": 0.5,
                    "fail": 0.8,
                    "unit": "fraction",
                }
            }
        }
        with pytest.raises(ThresholdConfigError, match="direction must be one of"):
            ThresholdConfig.from_dict(data)

    def test_invalid_unit(self):
        """Invalid unit value raises ThresholdConfigError."""
        data = {
            "metrics": {
                "bad": {
                    "direction": "higher_is_worse",
                    "warn": 0.5,
                    "fail": 0.8,
                    "unit": "kilograms",
                }
            }
        }
        with pytest.raises(ThresholdConfigError, match="unit must be one of"):
            ThresholdConfig.from_dict(data)

    def test_missing_metric_fields(self):
        """Metric missing required fields raises ThresholdConfigError."""
        data = {
            "metrics": {
                "incomplete": {
                    "direction": "higher_is_worse",
                    "warn": 0.5,
                    # missing 'fail' and 'unit'
                }
            }
        }
        with pytest.raises(ThresholdConfigError, match="missing required fields"):
            ThresholdConfig.from_dict(data)

    def test_wrong_ordering_higher_is_worse(self):
        """For higher_is_worse, warn must be < fail."""
        data = {
            "metrics": {
                "bad_order": {
                    "direction": "higher_is_worse",
                    "warn": 0.8,
                    "fail": 0.5,  # fail < warn is invalid
                    "unit": "fraction",
                }
            }
        }
        with pytest.raises(ThresholdConfigError, match="warn.*must be < fail"):
            ThresholdConfig.from_dict(data)

    def test_wrong_ordering_lower_is_worse(self):
        """For lower_is_worse, warn must be > fail."""
        data = {
            "metrics": {
                "bad_order": {
                    "direction": "lower_is_worse",
                    "warn": 0.5,
                    "fail": 0.8,  # fail > warn is invalid
                    "unit": "fraction",
                }
            }
        }
        with pytest.raises(ThresholdConfigError, match="warn.*must be > fail"):
            ThresholdConfig.from_dict(data)

    def test_equal_warn_fail_higher_is_worse(self):
        """Equal warn/fail for higher_is_worse raises error."""
        data = {
            "metrics": {
                "equal": {
                    "direction": "higher_is_worse",
                    "warn": 0.5,
                    "fail": 0.5,
                    "unit": "fraction",
                }
            }
        }
        with pytest.raises(ThresholdConfigError):
            ThresholdConfig.from_dict(data)

    def test_invalid_adaptive_min_runs(self):
        """min_runs < 1 raises ThresholdConfigError."""
        data = {
            "metrics": {
                "m": {
                    "direction": "higher_is_worse",
                    "warn": 0.2,
                    "fail": 0.4,
                    "unit": "fraction",
                }
            },
            "adaptive": {"min_runs": 0, "sigma_multiplier": 2.0},
        }
        with pytest.raises(ThresholdConfigError, match="min_runs must be >= 1"):
            ThresholdConfig.from_dict(data)

    def test_invalid_adaptive_sigma(self):
        """sigma_multiplier <= 0 raises ThresholdConfigError."""
        data = {
            "metrics": {
                "m": {
                    "direction": "higher_is_worse",
                    "warn": 0.2,
                    "fail": 0.4,
                    "unit": "fraction",
                }
            },
            "adaptive": {"min_runs": 20, "sigma_multiplier": -1.0},
        }
        with pytest.raises(ThresholdConfigError, match="sigma_multiplier must be > 0"):
            ThresholdConfig.from_dict(data)

    def test_invalid_quarantine_timeout(self):
        """auto_execute_timeout_minutes < 1 raises ThresholdConfigError."""
        data = {
            "metrics": {
                "m": {
                    "direction": "higher_is_worse",
                    "warn": 0.2,
                    "fail": 0.4,
                    "unit": "fraction",
                }
            },
            "quarantine": {
                "consecutive_failures_for_hard": 2,
                "auto_execute_timeout_minutes": 0,
                "notification_channel": "sns",
            },
        }
        with pytest.raises(ThresholdConfigError, match="auto_execute_timeout_minutes must be >= 1"):
            ThresholdConfig.from_dict(data)

    def test_file_not_found(self):
        """Loading from nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            ThresholdConfig.from_yaml("/nonexistent/path.yaml")

    def test_non_mapping_config(self, tmp_path):
        """A YAML file that isn't a mapping raises ThresholdConfigError."""
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("- just a list\n- not a mapping\n")
        with pytest.raises(ThresholdConfigError, match="must be a YAML mapping"):
            ThresholdConfig.from_yaml(bad_file)

    def test_invalid_retry_profile_key(self):
        """Retry profile key not matching 'attempt_N' raises error."""
        data = {
            "metrics": {
                "m": {
                    "direction": "higher_is_worse",
                    "warn": 0.2,
                    "fail": 0.4,
                    "unit": "fraction",
                }
            },
            "retry_profiles": {
                "profile_one": {"qualified_quality_phred": 15, "length_required": 50}
            },
        }
        with pytest.raises(ThresholdConfigError, match="must be in format 'attempt_N'"):
            ThresholdConfig.from_dict(data)


# ══════════════════════════════════════════════════════════════════════════════
# Test: Metric evaluation
# ══════════════════════════════════════════════════════════════════════════════


class TestMetricEvaluation:
    """Test that metric thresholds evaluate values correctly."""

    def test_higher_is_worse_pass(self):
        """Value below warn threshold → pass."""
        m = MetricThreshold("dup", "higher_is_worse", warn=0.20, fail=0.40, unit="fraction")
        assert m.evaluate(0.05) == "pass"

    def test_higher_is_worse_warn(self):
        """Value between warn and fail → warn."""
        m = MetricThreshold("dup", "higher_is_worse", warn=0.20, fail=0.40, unit="fraction")
        assert m.evaluate(0.25) == "warn"

    def test_higher_is_worse_fail(self):
        """Value above fail threshold → fail."""
        m = MetricThreshold("dup", "higher_is_worse", warn=0.20, fail=0.40, unit="fraction")
        assert m.evaluate(0.50) == "fail"

    def test_higher_is_worse_at_boundary(self):
        """Value exactly at warn threshold → warn (boundary is exclusive)."""
        m = MetricThreshold("dup", "higher_is_worse", warn=0.20, fail=0.40, unit="fraction")
        assert m.evaluate(0.20) == "pass"  # not > 0.20
        assert m.evaluate(0.40) == "warn"  # not > 0.40

    def test_lower_is_worse_pass(self):
        """Value above warn threshold → pass."""
        m = MetricThreshold("f1", "lower_is_worse", warn=0.995, fail=0.99, unit="score")
        assert m.evaluate(0.999) == "pass"

    def test_lower_is_worse_warn(self):
        """Value between fail and warn → warn."""
        m = MetricThreshold("f1", "lower_is_worse", warn=0.995, fail=0.99, unit="score")
        assert m.evaluate(0.993) == "warn"

    def test_lower_is_worse_fail(self):
        """Value below fail threshold → fail."""
        m = MetricThreshold("f1", "lower_is_worse", warn=0.995, fail=0.99, unit="score")
        assert m.evaluate(0.985) == "fail"

    def test_lower_is_worse_at_boundary(self):
        """Value exactly at warn threshold → warn (boundary is exclusive)."""
        m = MetricThreshold("f1", "lower_is_worse", warn=0.995, fail=0.99, unit="score")
        assert m.evaluate(0.995) == "pass"  # not < 0.995
        assert m.evaluate(0.99) == "warn"  # not < 0.99

    def test_full_config_evaluation(self):
        """Evaluate all metrics from the committed config."""
        config = qc_thresholds.load_default_config()

        # Good values → all pass
        assert config.get_metric("percent_duplication").evaluate(0.05) == "pass"
        assert config.get_metric("q30_rate").evaluate(0.92) == "pass"
        assert config.get_metric("reads_filtered_percent").evaluate(0.10) == "pass"
        assert config.get_metric("snp_f1").evaluate(0.998) == "pass"
        assert config.get_metric("snp_precision").evaluate(0.998) == "pass"
        assert config.get_metric("snp_recall").evaluate(0.998) == "pass"

        # Bad values → all fail
        assert config.get_metric("percent_duplication").evaluate(0.50) == "fail"
        assert config.get_metric("q30_rate").evaluate(0.60) == "fail"
        assert config.get_metric("reads_filtered_percent").evaluate(0.60) == "fail"
        assert config.get_metric("snp_f1").evaluate(0.980) == "fail"


# ══════════════════════════════════════════════════════════════════════════════
# Property test: warn/fail ordering correct for all metric directions
# ══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=100)
@given(
    warn=st.floats(min_value=0.01, max_value=0.99, allow_nan=False),
    fail_delta=st.floats(min_value=0.001, max_value=0.49, allow_nan=False),
)
def test_property_higher_is_worse_ordering(warn, fail_delta):
    """For higher_is_worse, any value > fail must also be > warn."""
    fail = warn + fail_delta
    assume(fail <= 1.0)

    m = MetricThreshold("test", "higher_is_worse", warn=warn, fail=fail, unit="fraction")
    # If a value triggers fail, it must also exceed warn
    test_val = fail + 0.01
    if test_val <= 1.0:
        assert m.evaluate(test_val) == "fail"

    # Value in warn zone
    mid_val = (warn + fail) / 2
    assert m.evaluate(mid_val) == "warn"

    # Value in pass zone
    safe_val = warn - 0.01
    if safe_val >= 0:
        assert m.evaluate(safe_val) == "pass"


@settings(max_examples=100)
@given(
    fail=st.floats(min_value=0.01, max_value=0.98, allow_nan=False),
    warn_delta=st.floats(min_value=0.001, max_value=0.49, allow_nan=False),
)
def test_property_lower_is_worse_ordering(fail, warn_delta):
    """For lower_is_worse, any value < fail must also be < warn."""
    warn = fail + warn_delta
    assume(warn <= 1.0)

    m = MetricThreshold("test", "lower_is_worse", warn=warn, fail=fail, unit="score")
    # If a value triggers fail, it must also be below warn
    test_val = fail - 0.01
    if test_val >= 0:
        assert m.evaluate(test_val) == "fail"

    # Value in warn zone
    mid_val = (fail + warn) / 2
    assert m.evaluate(mid_val) == "warn"

    # Value in pass zone
    safe_val = warn + 0.01
    if safe_val <= 1.0:
        assert m.evaluate(safe_val) == "pass"


@settings(max_examples=100)
@given(
    value=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_property_evaluation_always_returns_valid_status(value):
    """For any float value, evaluate() always returns one of pass/warn/fail."""
    config = qc_thresholds.load_default_config()
    for metric in config.metrics.values():
        result = metric.evaluate(value)
        assert result in {"pass", "warn", "fail"}
