#!/usr/bin/env python3
"""QC Thresholds Configuration Loader and Validator.

Loads qc_thresholds.yaml, validates all fields, and provides a typed interface
for downstream QC evaluation. Raises on invalid or inconsistent configuration.

Requirements: Adaptive thresholds, retry profiles, quarantine rules.
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

VALID_DIRECTIONS = {"higher_is_worse", "lower_is_worse"}
VALID_UNITS = {"fraction", "score", "percent"}
REQUIRED_METRIC_FIELDS = {"direction", "warn", "fail", "unit"}
REQUIRED_ADAPTIVE_FIELDS = {"min_runs", "sigma_multiplier"}
REQUIRED_QUARANTINE_FIELDS = {
    "consecutive_failures_for_hard",
    "auto_execute_timeout_minutes",
    "notification_channel",
}


class ThresholdConfigError(Exception):
    """Raised when the QC threshold configuration is invalid."""


@dataclass
class MetricThreshold:
    """Threshold definition for a single QC metric."""

    name: str
    direction: str
    warn: float
    fail: float
    unit: str

    def __post_init__(self):
        if self.direction not in VALID_DIRECTIONS:
            raise ThresholdConfigError(
                f"Metric '{self.name}': direction must be one of {VALID_DIRECTIONS}, "
                f"got '{self.direction}'"
            )
        if self.unit not in VALID_UNITS:
            raise ThresholdConfigError(
                f"Metric '{self.name}': unit must be one of {VALID_UNITS}, "
                f"got '{self.unit}'"
            )
        self._validate_ordering()

    def _validate_ordering(self):
        """Ensure warn/fail thresholds are ordered correctly for the direction."""
        if self.direction == "higher_is_worse":
            # warn < fail (both are upper bounds; fail is worse = higher)
            if self.warn >= self.fail:
                raise ThresholdConfigError(
                    f"Metric '{self.name}' (higher_is_worse): "
                    f"warn ({self.warn}) must be < fail ({self.fail})"
                )
        else:
            # lower_is_worse: warn > fail (both are lower bounds; fail is worse = lower)
            if self.warn <= self.fail:
                raise ThresholdConfigError(
                    f"Metric '{self.name}' (lower_is_worse): "
                    f"warn ({self.warn}) must be > fail ({self.fail})"
                )

    def evaluate(self, value: float) -> str:
        """Evaluate a metric value against thresholds.

        Returns:
            "pass", "warn", or "fail"
        """
        if self.direction == "higher_is_worse":
            if value > self.fail:
                return "fail"
            if value > self.warn:
                return "warn"
            return "pass"
        else:
            if value < self.fail:
                return "fail"
            if value < self.warn:
                return "warn"
            return "pass"


@dataclass
class RetryProfile:
    """Fastp parameters for a specific retry attempt."""

    attempt: int
    qualified_quality_phred: int
    length_required: int
    detect_adapter_for_pe: bool = True
    trim_poly_g: bool = False
    cut_front: bool = False
    cut_tail: bool = False
    cut_window_size: int | None = None
    cut_mean_quality: int | None = None
    description: str = ""


@dataclass
class AdaptiveConfig:
    """Configuration for adaptive threshold calculation."""

    min_runs: int
    sigma_multiplier: float

    def __post_init__(self):
        if self.min_runs < 1:
            raise ThresholdConfigError(
                f"adaptive.min_runs must be >= 1, got {self.min_runs}"
            )
        if self.sigma_multiplier <= 0:
            raise ThresholdConfigError(
                f"adaptive.sigma_multiplier must be > 0, got {self.sigma_multiplier}"
            )


@dataclass
class QuarantineConfig:
    """Configuration for quarantine escalation."""

    consecutive_failures_for_hard: int
    auto_execute_timeout_minutes: int
    notification_channel: str

    def __post_init__(self):
        if self.consecutive_failures_for_hard < 1:
            raise ThresholdConfigError(
                f"quarantine.consecutive_failures_for_hard must be >= 1, "
                f"got {self.consecutive_failures_for_hard}"
            )
        if self.auto_execute_timeout_minutes < 1:
            raise ThresholdConfigError(
                f"quarantine.auto_execute_timeout_minutes must be >= 1, "
                f"got {self.auto_execute_timeout_minutes}"
            )


@dataclass
class ThresholdConfig:
    """Complete QC threshold configuration loaded from YAML."""

    metrics: dict[str, MetricThreshold] = field(default_factory=dict)
    adaptive: AdaptiveConfig = field(default_factory=lambda: AdaptiveConfig(20, 2.0))
    quarantine: QuarantineConfig = field(
        default_factory=lambda: QuarantineConfig(2, 10, "sns")
    )
    retry_profiles: dict[int, RetryProfile] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ThresholdConfig":
        """Load and validate configuration from a YAML file.

        Args:
            path: Path to qc_thresholds.yaml

        Returns:
            Validated ThresholdConfig instance.

        Raises:
            ThresholdConfigError: If configuration is invalid.
            FileNotFoundError: If the file doesn't exist.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"QC threshold config not found: {path}")

        with open(path) as fh:
            raw = yaml.safe_load(fh)

        if not isinstance(raw, dict):
            raise ThresholdConfigError("Config file must be a YAML mapping")

        return cls._from_dict(raw)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThresholdConfig":
        """Load and validate configuration from a dictionary.

        Args:
            data: Configuration dictionary (same structure as YAML).

        Returns:
            Validated ThresholdConfig instance.

        Raises:
            ThresholdConfigError: If configuration is invalid.
        """
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, raw: dict[str, Any]) -> "ThresholdConfig":
        """Internal: parse and validate a configuration dictionary."""
        # Validate top-level keys
        if "metrics" not in raw:
            raise ThresholdConfigError("Missing required top-level key: 'metrics'")

        # Parse metrics
        metrics = {}
        for name, mconf in raw["metrics"].items():
            if not isinstance(mconf, dict):
                raise ThresholdConfigError(
                    f"Metric '{name}' must be a mapping, got {type(mconf).__name__}"
                )
            missing = REQUIRED_METRIC_FIELDS - set(mconf.keys())
            if missing:
                raise ThresholdConfigError(
                    f"Metric '{name}' missing required fields: {missing}"
                )
            metrics[name] = MetricThreshold(
                name=name,
                direction=mconf["direction"],
                warn=float(mconf["warn"]),
                fail=float(mconf["fail"]),
                unit=mconf["unit"],
            )

        # Parse adaptive config
        adaptive_raw = raw.get("adaptive", {"min_runs": 20, "sigma_multiplier": 2.0})
        if not isinstance(adaptive_raw, dict):
            raise ThresholdConfigError("'adaptive' must be a mapping")
        missing = REQUIRED_ADAPTIVE_FIELDS - set(adaptive_raw.keys())
        if missing:
            raise ThresholdConfigError(
                f"'adaptive' section missing required fields: {missing}"
            )
        adaptive = AdaptiveConfig(
            min_runs=int(adaptive_raw["min_runs"]),
            sigma_multiplier=float(adaptive_raw["sigma_multiplier"]),
        )

        # Parse quarantine config
        quarantine_raw = raw.get(
            "quarantine",
            {
                "consecutive_failures_for_hard": 2,
                "auto_execute_timeout_minutes": 10,
                "notification_channel": "sns",
            },
        )
        if not isinstance(quarantine_raw, dict):
            raise ThresholdConfigError("'quarantine' must be a mapping")
        missing = REQUIRED_QUARANTINE_FIELDS - set(quarantine_raw.keys())
        if missing:
            raise ThresholdConfigError(
                f"'quarantine' section missing required fields: {missing}"
            )
        quarantine = QuarantineConfig(
            consecutive_failures_for_hard=int(
                quarantine_raw["consecutive_failures_for_hard"]
            ),
            auto_execute_timeout_minutes=int(
                quarantine_raw["auto_execute_timeout_minutes"]
            ),
            notification_channel=str(quarantine_raw["notification_channel"]),
        )

        # Parse retry profiles
        retry_profiles = {}
        for key, profile_raw in raw.get("retry_profiles", {}).items():
            # Extract attempt number from key like "attempt_1"
            try:
                attempt_num = int(key.split("_")[-1])
            except (ValueError, IndexError):
                raise ThresholdConfigError(
                    f"Retry profile key '{key}' must be in format 'attempt_N'"
                )

            if not isinstance(profile_raw, dict):
                raise ThresholdConfigError(
                    f"Retry profile '{key}' must be a mapping"
                )

            retry_profiles[attempt_num] = RetryProfile(
                attempt=attempt_num,
                qualified_quality_phred=int(
                    profile_raw.get("qualified_quality_phred", 15)
                ),
                length_required=int(profile_raw.get("length_required", 50)),
                detect_adapter_for_pe=bool(
                    profile_raw.get("detect_adapter_for_pe", True)
                ),
                trim_poly_g=bool(profile_raw.get("trim_poly_g", False)),
                cut_front=bool(profile_raw.get("cut_front", False)),
                cut_tail=bool(profile_raw.get("cut_tail", False)),
                cut_window_size=(
                    int(profile_raw["cut_window_size"])
                    if "cut_window_size" in profile_raw
                    else None
                ),
                cut_mean_quality=(
                    int(profile_raw["cut_mean_quality"])
                    if "cut_mean_quality" in profile_raw
                    else None
                ),
                description=str(profile_raw.get("description", "")),
            )

        return cls(
            metrics=metrics,
            adaptive=adaptive,
            quarantine=quarantine,
            retry_profiles=retry_profiles,
        )

    def get_metric(self, name: str) -> MetricThreshold:
        """Get threshold config for a named metric.

        Raises:
            KeyError: If metric name is not configured.
        """
        if name not in self.metrics:
            raise KeyError(f"Unknown QC metric: '{name}'. Available: {list(self.metrics.keys())}")
        return self.metrics[name]

    def get_retry_profile(self, attempt: int) -> RetryProfile:
        """Get retry profile for a given attempt number.

        Falls back to the highest configured attempt if requested attempt exceeds max.

        Args:
            attempt: Attempt number (1-indexed).

        Returns:
            RetryProfile for the given attempt.
        """
        if attempt in self.retry_profiles:
            return self.retry_profiles[attempt]
        # Fall back to highest configured attempt
        max_attempt = max(self.retry_profiles.keys()) if self.retry_profiles else 1
        return self.retry_profiles.get(
            min(attempt, max_attempt),
            RetryProfile(attempt=attempt, qualified_quality_phred=15, length_required=50),
        )


# Convenience: default config path relative to the pipeline root
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "conf" / "qc_thresholds.yaml"


def load_default_config() -> ThresholdConfig:
    """Load the default QC threshold config from pipeline/conf/qc_thresholds.yaml."""
    return ThresholdConfig.from_yaml(DEFAULT_CONFIG_PATH)


if __name__ == "__main__":
    # CLI: validate the config and print a summary
    config_path = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_CONFIG_PATH)
    try:
        config = ThresholdConfig.from_yaml(config_path)
        print(f"✓ Config valid: {config_path}")
        print(f"  Metrics: {list(config.metrics.keys())}")
        print(f"  Adaptive: min_runs={config.adaptive.min_runs}, σ={config.adaptive.sigma_multiplier}")
        print(f"  Retry profiles: {list(config.retry_profiles.keys())}")
        print(f"  Quarantine: hard after {config.quarantine.consecutive_failures_for_hard} failures")
    except (ThresholdConfigError, FileNotFoundError) as e:
        print(f"✗ Config invalid: {e}", file=sys.stderr)
        sys.exit(1)
