#!/usr/bin/env python3
"""Adaptive Threshold Calculator for QC Metrics.

Computes mean ± 2σ thresholds from historical run data, falling back to
bootstrap defaults (from qc_thresholds.yaml) when fewer than min_runs
historical data points are available.

Usage:
    calculator = AdaptiveThresholdCalculator(config, history)
    result = calculator.evaluate("percent_duplication", 0.065)
    thresholds = calculator.get_thresholds("snp_f1")
"""
import math
import statistics
from dataclasses import dataclass
from typing import Sequence

from qc_thresholds import MetricThreshold, ThresholdConfig, load_default_config


@dataclass(frozen=True)
class ThresholdResult:
    """Result of threshold computation for a metric."""

    warn: float
    fail: float
    source: str  # "adaptive" or "bootstrap"
    mean: float | None = None
    std: float | None = None
    n_samples: int = 0


class AdaptiveThresholdCalculator:
    """Computes adaptive QC thresholds from historical data.

    When sufficient history exists (>= min_runs), thresholds are computed as:
      - higher_is_worse: warn = mean + σ*multiplier, fail = mean + 2*σ*multiplier
      - lower_is_worse:  warn = mean - σ*multiplier, fail = mean - 2*σ*multiplier

    When insufficient history exists, falls back to bootstrap defaults from config.
    """

    def __init__(
        self,
        config: ThresholdConfig | None = None,
        history: dict[str, list[float]] | None = None,
    ):
        """Initialize the adaptive threshold calculator.

        Args:
            config: QC threshold configuration (loaded from YAML). Uses default if None.
            history: Dict mapping metric names to lists of historical values.
                     Example: {"percent_duplication": [0.05, 0.06, 0.04, ...]}
        """
        self._config = config or load_default_config()
        self._history: dict[str, list[float]] = history or {}

    @property
    def config(self) -> ThresholdConfig:
        return self._config

    def add_observation(self, metric_name: str, value: float) -> None:
        """Add a historical observation for a metric.

        Args:
            metric_name: Name of the QC metric.
            value: Observed metric value.
        """
        if metric_name not in self._history:
            self._history[metric_name] = []
        self._history[metric_name].append(value)

    def add_observations(self, metric_name: str, values: Sequence[float]) -> None:
        """Add multiple historical observations for a metric.

        Args:
            metric_name: Name of the QC metric.
            values: Sequence of observed metric values.
        """
        if metric_name not in self._history:
            self._history[metric_name] = []
        self._history[metric_name].extend(values)

    def get_history(self, metric_name: str) -> list[float]:
        """Get the historical values for a metric."""
        return list(self._history.get(metric_name, []))

    def _has_sufficient_history(self, metric_name: str) -> bool:
        """Check if enough historical data exists for adaptive thresholds."""
        values = self._history.get(metric_name, [])
        return len(values) >= self._config.adaptive.min_runs

    def _compute_stats(self, values: list[float]) -> tuple[float, float]:
        """Compute mean and standard deviation of a sample.

        Args:
            values: List of metric values (must have len >= 2).

        Returns:
            Tuple of (mean, stdev). Returns (mean, 0.0) if stdev is 0 or NaN.
        """
        mean = statistics.mean(values)
        if len(values) < 2:
            return mean, 0.0
        stdev = statistics.stdev(values)
        # Guard against NaN/inf from degenerate data
        if math.isnan(stdev) or math.isinf(stdev):
            return mean, 0.0
        return mean, stdev

    def get_thresholds(self, metric_name: str) -> ThresholdResult:
        """Get the current thresholds for a metric (adaptive or bootstrap).

        Args:
            metric_name: Name of the QC metric.

        Returns:
            ThresholdResult with warn/fail values and source indicator.

        Raises:
            KeyError: If metric_name is not in the configuration.
        """
        # Ensure metric is configured
        bootstrap = self._config.get_metric(metric_name)
        values = self._history.get(metric_name, [])

        if not self._has_sufficient_history(metric_name):
            return ThresholdResult(
                warn=bootstrap.warn,
                fail=bootstrap.fail,
                source="bootstrap",
                mean=statistics.mean(values) if values else None,
                std=statistics.stdev(values) if len(values) >= 2 else None,
                n_samples=len(values),
            )

        mean, stdev = self._compute_stats(values)
        sigma = self._config.adaptive.sigma_multiplier

        # If σ = 0 (all values identical), fall back to bootstrap.
        # Adaptive thresholds are meaningless without variance.
        if stdev == 0.0:
            return ThresholdResult(
                warn=bootstrap.warn,
                fail=bootstrap.fail,
                source="bootstrap",
                mean=mean,
                std=0.0,
                n_samples=len(values),
            )

        # Compute adaptive thresholds based on direction
        if bootstrap.direction == "higher_is_worse":
            warn = mean + sigma * stdev
            fail = mean + 2 * sigma * stdev
        else:
            # lower_is_worse
            warn = mean - sigma * stdev
            fail = mean - 2 * sigma * stdev

        # Clamp thresholds to valid ranges
        warn = self._clamp_threshold(warn, bootstrap)
        fail = self._clamp_threshold(fail, bootstrap)

        return ThresholdResult(
            warn=warn,
            fail=fail,
            source="adaptive",
            mean=mean,
            std=stdev,
            n_samples=len(values),
        )

    def _clamp_threshold(self, value: float, metric: MetricThreshold) -> float:
        """Clamp a threshold value to sensible bounds.

        For fractions/scores: clamp to [0, 1].
        Prevents nonsensical thresholds from extreme distributions.
        """
        if metric.unit in ("fraction", "score"):
            return max(0.0, min(1.0, value))
        return value

    def evaluate(self, metric_name: str, value: float) -> str:
        """Evaluate a metric value against adaptive/bootstrap thresholds.

        Args:
            metric_name: Name of the QC metric.
            value: Current observed value.

        Returns:
            "pass", "warn", or "fail"

        Raises:
            KeyError: If metric_name is not in the configuration.
        """
        bootstrap = self._config.get_metric(metric_name)
        thresholds = self.get_thresholds(metric_name)

        # Use the same evaluation logic as MetricThreshold but with adaptive values
        if bootstrap.direction == "higher_is_worse":
            if value > thresholds.fail:
                return "fail"
            if value > thresholds.warn:
                return "warn"
            return "pass"
        else:
            # lower_is_worse
            if value < thresholds.fail:
                return "fail"
            if value < thresholds.warn:
                return "warn"
            return "pass"

    def evaluate_all(self, metrics: dict[str, float]) -> dict[str, dict]:
        """Evaluate multiple metrics at once.

        Args:
            metrics: Dict mapping metric names to observed values.

        Returns:
            Dict mapping metric names to evaluation results with keys:
            value, status, thresholds (warn, fail, source).
        """
        results = {}
        for name, value in metrics.items():
            if name not in self._config.metrics:
                continue
            thresholds = self.get_thresholds(name)
            status = self.evaluate(name, value)
            results[name] = {
                "value": value,
                "status": status,
                "warn_threshold": thresholds.warn,
                "fail_threshold": thresholds.fail,
                "source": thresholds.source,
            }
        return results
