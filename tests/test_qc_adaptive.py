"""Tests for Adaptive Threshold Calculator.

Validates:
- 20+ values → adaptive thresholds with correct mean ± 2σ
- <20 values → bootstrap defaults
- Edge cases: all identical (σ=0 → bootstrap), single outlier handled gracefully
- evaluate() and evaluate_all() produce correct results
"""
import importlib.util
import math
import statistics
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]


def _load(module_path: Path, name: str):
    import sys
    # Ensure the pipeline/bin directory is in sys.path for inter-module imports
    bin_dir = str(ROOT / "pipeline" / "bin")
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    spec = importlib.util.spec_from_file_location(name, module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


qc_adaptive = _load(ROOT / "pipeline" / "bin" / "qc_adaptive.py", "qc_adaptive")
qc_thresholds = _load(ROOT / "pipeline" / "bin" / "qc_thresholds.py", "qc_thresholds")

AdaptiveThresholdCalculator = qc_adaptive.AdaptiveThresholdCalculator
ThresholdResult = qc_adaptive.ThresholdResult
ThresholdConfig = qc_thresholds.ThresholdConfig


def _make_config() -> ThresholdConfig:
    """Load the default config."""
    return qc_thresholds.load_default_config()


# ══════════════════════════════════════════════════════════════════════════════
# Test: Adaptive thresholds with 20+ values
# ══════════════════════════════════════════════════════════════════════════════


class TestAdaptiveMode:
    """Test adaptive threshold computation with sufficient history."""

    def test_adaptive_with_25_values(self):
        """25 values → adaptive thresholds with mean ± 2σ."""
        config = _make_config()
        # Generate 25 values around 0.05 (typical duplication rate)
        values = [0.05 + i * 0.001 for i in range(25)]
        history = {"percent_duplication": values}

        calc = AdaptiveThresholdCalculator(config, history)
        result = calc.get_thresholds("percent_duplication")

        assert result.source == "adaptive"
        assert result.n_samples == 25
        assert result.mean is not None
        assert result.std is not None
        assert result.std > 0

        # Verify: warn = mean + 2*σ, fail = mean + 4*σ (sigma_multiplier=2.0)
        expected_mean = statistics.mean(values)
        expected_std = statistics.stdev(values)
        expected_warn = expected_mean + 2.0 * expected_std
        expected_fail = expected_mean + 2 * 2.0 * expected_std

        assert math.isclose(result.warn, expected_warn, rel_tol=1e-9)
        assert math.isclose(result.fail, expected_fail, rel_tol=1e-9)

    def test_adaptive_lower_is_worse(self):
        """Adaptive thresholds for lower_is_worse metrics subtract from mean."""
        config = _make_config()
        # Generate 25 values around 0.998 (typical F1)
        values = [0.998 + i * 0.0001 for i in range(25)]
        history = {"snp_f1": values}

        calc = AdaptiveThresholdCalculator(config, history)
        result = calc.get_thresholds("snp_f1")

        assert result.source == "adaptive"
        expected_mean = statistics.mean(values)
        expected_std = statistics.stdev(values)
        expected_warn = expected_mean - 2.0 * expected_std
        expected_fail = expected_mean - 2 * 2.0 * expected_std

        assert math.isclose(result.warn, expected_warn, rel_tol=1e-9)
        assert math.isclose(result.fail, expected_fail, rel_tol=1e-9)

    def test_adaptive_evaluation_pass(self):
        """Values within normal range evaluate as pass."""
        config = _make_config()
        values = [0.05] * 25  # all 0.05 → σ=0 → bootstrap fallback
        # Use varied values to get real adaptive
        values = [0.04 + i * 0.001 for i in range(25)]
        history = {"percent_duplication": values}

        calc = AdaptiveThresholdCalculator(config, history)
        mean = statistics.mean(values)
        # Value at the mean should pass
        assert calc.evaluate("percent_duplication", mean) == "pass"

    def test_adaptive_evaluation_warn(self):
        """Values beyond 1σ from mean evaluate as warn in adaptive mode."""
        config = _make_config()
        values = [0.05 + i * 0.002 for i in range(25)]
        history = {"percent_duplication": values}

        calc = AdaptiveThresholdCalculator(config, history)
        result = calc.get_thresholds("percent_duplication")
        # Value between warn and fail triggers warn
        mid = (result.warn + result.fail) / 2
        assert calc.evaluate("percent_duplication", mid) == "warn"

    def test_adaptive_evaluation_fail(self):
        """Values beyond 2σ from mean evaluate as fail in adaptive mode."""
        config = _make_config()
        values = [0.05 + i * 0.002 for i in range(25)]
        history = {"percent_duplication": values}

        calc = AdaptiveThresholdCalculator(config, history)
        result = calc.get_thresholds("percent_duplication")
        # Value above fail triggers fail
        assert calc.evaluate("percent_duplication", result.fail + 0.01) == "fail"


# ══════════════════════════════════════════════════════════════════════════════
# Test: Bootstrap fallback with <20 values
# ══════════════════════════════════════════════════════════════════════════════


class TestBootstrapFallback:
    """Test fallback to bootstrap defaults when insufficient history."""

    def test_empty_history(self):
        """No history → bootstrap defaults."""
        config = _make_config()
        calc = AdaptiveThresholdCalculator(config, {})
        result = calc.get_thresholds("percent_duplication")

        assert result.source == "bootstrap"
        assert result.warn == 0.20
        assert result.fail == 0.40
        assert result.n_samples == 0
        assert result.mean is None

    def test_fewer_than_20_values(self):
        """10 values → bootstrap defaults."""
        config = _make_config()
        history = {"percent_duplication": [0.05] * 10}
        calc = AdaptiveThresholdCalculator(config, history)
        result = calc.get_thresholds("percent_duplication")

        assert result.source == "bootstrap"
        assert result.warn == 0.20
        assert result.fail == 0.40
        assert result.n_samples == 10

    def test_exactly_19_values(self):
        """Exactly 19 values → still bootstrap."""
        config = _make_config()
        history = {"percent_duplication": [0.05] * 19}
        calc = AdaptiveThresholdCalculator(config, history)
        result = calc.get_thresholds("percent_duplication")

        assert result.source == "bootstrap"

    def test_exactly_20_values_switches_to_adaptive(self):
        """Exactly 20 values (with variance) → adaptive mode."""
        config = _make_config()
        values = [0.04 + i * 0.001 for i in range(20)]
        history = {"percent_duplication": values}
        calc = AdaptiveThresholdCalculator(config, history)
        result = calc.get_thresholds("percent_duplication")

        assert result.source == "adaptive"
        assert result.n_samples == 20

    def test_bootstrap_evaluation_matches_config(self):
        """Bootstrap evaluation matches static threshold evaluation."""
        config = _make_config()
        calc = AdaptiveThresholdCalculator(config, {})

        # These should match the static config thresholds
        assert calc.evaluate("percent_duplication", 0.05) == "pass"
        assert calc.evaluate("percent_duplication", 0.25) == "warn"
        assert calc.evaluate("percent_duplication", 0.50) == "fail"

    def test_metric_not_in_history(self):
        """Metric with no history key → bootstrap."""
        config = _make_config()
        history = {"some_other_metric": [1.0] * 30}
        calc = AdaptiveThresholdCalculator(config, history)
        result = calc.get_thresholds("snp_f1")

        assert result.source == "bootstrap"
        assert result.warn == 0.995
        assert result.fail == 0.99


# ══════════════════════════════════════════════════════════════════════════════
# Test: Edge cases
# ══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Test edge cases: σ=0, single outlier, clamping."""

    def test_all_identical_values_falls_back(self):
        """All identical values → σ=0 → bootstrap fallback."""
        config = _make_config()
        history = {"percent_duplication": [0.05] * 30}
        calc = AdaptiveThresholdCalculator(config, history)
        result = calc.get_thresholds("percent_duplication")

        # σ = 0 means adaptive is meaningless → falls back to bootstrap
        assert result.source == "bootstrap"
        assert result.std == 0.0
        assert result.mean == 0.05
        assert result.n_samples == 30

    def test_single_outlier_handled(self):
        """A single outlier doesn't cause errors; thresholds still computed."""
        config = _make_config()
        values = [0.05] * 24 + [0.90]  # one extreme outlier
        history = {"percent_duplication": values}
        calc = AdaptiveThresholdCalculator(config, history)
        result = calc.get_thresholds("percent_duplication")

        # Should still compute (outlier inflates σ)
        assert result.source == "adaptive"
        assert result.n_samples == 25
        assert result.std > 0
        # The outlier inflates mean and σ significantly
        assert result.mean > 0.05

    def test_thresholds_clamped_to_valid_range(self):
        """Thresholds are clamped to [0, 1] for fraction/score units."""
        config = _make_config()
        # Values very close to 1.0 → adaptive warn/fail could exceed 1.0
        values = [0.98 + i * 0.001 for i in range(25)]
        history = {"percent_duplication": values}
        calc = AdaptiveThresholdCalculator(config, history)
        result = calc.get_thresholds("percent_duplication")

        assert result.warn <= 1.0
        assert result.fail <= 1.0

    def test_lower_is_worse_thresholds_clamped_above_zero(self):
        """Lower-is-worse thresholds don't go below 0."""
        config = _make_config()
        # Values near 0 with large spread → fail could go negative
        values = [0.01 + i * 0.005 for i in range(25)]
        history = {"q30_rate": values}
        calc = AdaptiveThresholdCalculator(config, history)
        result = calc.get_thresholds("q30_rate")

        assert result.warn >= 0.0
        assert result.fail >= 0.0

    def test_add_observation_increments_history(self):
        """add_observation correctly adds values."""
        config = _make_config()
        calc = AdaptiveThresholdCalculator(config, {})
        for i in range(25):
            calc.add_observation("percent_duplication", 0.04 + i * 0.001)

        result = calc.get_thresholds("percent_duplication")
        assert result.source == "adaptive"
        assert result.n_samples == 25

    def test_add_observations_bulk(self):
        """add_observations correctly adds multiple values."""
        config = _make_config()
        calc = AdaptiveThresholdCalculator(config, {})
        values = [0.04 + i * 0.001 for i in range(25)]
        calc.add_observations("percent_duplication", values)

        result = calc.get_thresholds("percent_duplication")
        assert result.source == "adaptive"
        assert result.n_samples == 25

    def test_unknown_metric_raises(self):
        """Evaluating an unknown metric raises KeyError."""
        config = _make_config()
        calc = AdaptiveThresholdCalculator(config, {})
        with pytest.raises(KeyError, match="Unknown QC metric"):
            calc.evaluate("nonexistent", 0.5)

    def test_get_history_returns_copy(self):
        """get_history returns a list (not exposing internal state)."""
        config = _make_config()
        history = {"percent_duplication": [0.05, 0.06]}
        calc = AdaptiveThresholdCalculator(config, history)
        h = calc.get_history("percent_duplication")
        assert h == [0.05, 0.06]
        # Modifying returned list doesn't affect internal state
        h.append(999)
        assert calc.get_history("percent_duplication") == [0.05, 0.06]


# ══════════════════════════════════════════════════════════════════════════════
# Test: evaluate_all
# ══════════════════════════════════════════════════════════════════════════════


class TestEvaluateAll:
    """Test batch evaluation of multiple metrics."""

    def test_evaluate_all_mixed_results(self):
        """evaluate_all returns per-metric results."""
        config = _make_config()
        calc = AdaptiveThresholdCalculator(config, {})
        results = calc.evaluate_all({
            "percent_duplication": 0.05,
            "snp_f1": 0.993,
            "q30_rate": 0.60,
        })

        assert results["percent_duplication"]["status"] == "pass"
        assert results["snp_f1"]["status"] == "warn"
        assert results["q30_rate"]["status"] == "fail"

    def test_evaluate_all_skips_unknown_metrics(self):
        """evaluate_all silently skips metrics not in config."""
        config = _make_config()
        calc = AdaptiveThresholdCalculator(config, {})
        results = calc.evaluate_all({
            "percent_duplication": 0.05,
            "unknown_metric": 42.0,
        })

        assert "percent_duplication" in results
        assert "unknown_metric" not in results

    def test_evaluate_all_includes_threshold_info(self):
        """evaluate_all results include threshold values and source."""
        config = _make_config()
        calc = AdaptiveThresholdCalculator(config, {})
        results = calc.evaluate_all({"percent_duplication": 0.05})

        r = results["percent_duplication"]
        assert "value" in r
        assert "status" in r
        assert "warn_threshold" in r
        assert "fail_threshold" in r
        assert "source" in r
        assert r["source"] == "bootstrap"
        assert r["warn_threshold"] == 0.20
        assert r["fail_threshold"] == 0.40


# ══════════════════════════════════════════════════════════════════════════════
# Property tests
# ══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=50)
@given(
    values=st.lists(
        st.floats(min_value=0.01, max_value=0.30, allow_nan=False, allow_infinity=False),
        min_size=20,
        max_size=50,
    ),
)
def test_property_adaptive_higher_is_worse_ordering(values):
    """For higher_is_worse with adaptive thresholds, warn < fail always holds."""
    config = _make_config()
    history = {"percent_duplication": values}
    calc = AdaptiveThresholdCalculator(config, history)
    result = calc.get_thresholds("percent_duplication")

    if result.source == "adaptive":
        assert result.warn < result.fail, (
            f"Adaptive warn ({result.warn}) must be < fail ({result.fail})"
        )


@settings(max_examples=50)
@given(
    values=st.lists(
        st.floats(min_value=0.95, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=20,
        max_size=50,
    ),
)
def test_property_adaptive_lower_is_worse_ordering(values):
    """For lower_is_worse with adaptive thresholds, warn > fail always holds."""
    config = _make_config()
    # Need variance for adaptive mode
    assume(statistics.stdev(values) > 0)
    history = {"snp_f1": values}
    calc = AdaptiveThresholdCalculator(config, history)
    result = calc.get_thresholds("snp_f1")

    if result.source == "adaptive":
        assert result.warn > result.fail, (
            f"Adaptive warn ({result.warn}) must be > fail ({result.fail})"
        )


@settings(max_examples=50)
@given(
    n_values=st.integers(min_value=0, max_value=50),
    test_value=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_property_evaluate_always_returns_valid_status(n_values, test_value):
    """evaluate() always returns one of pass/warn/fail regardless of history size."""
    config = _make_config()
    values = [0.05 + i * 0.001 for i in range(n_values)]
    history = {"percent_duplication": values} if n_values > 0 else {}
    calc = AdaptiveThresholdCalculator(config, history)
    result = calc.evaluate("percent_duplication", test_value)
    assert result in {"pass", "warn", "fail"}


@settings(max_examples=50)
@given(
    values=st.lists(
        st.floats(min_value=0.01, max_value=0.30, allow_nan=False, allow_infinity=False),
        min_size=20,
        max_size=50,
    ),
)
def test_property_adaptive_thresholds_clamped(values):
    """Adaptive thresholds for fraction metrics stay in [0, 1]."""
    config = _make_config()
    history = {"percent_duplication": values}
    calc = AdaptiveThresholdCalculator(config, history)
    result = calc.get_thresholds("percent_duplication")

    assert 0.0 <= result.warn <= 1.0
    assert 0.0 <= result.fail <= 1.0
