"""Tests for Retry Profiles in Nextflow Configuration.

Validates:
- Parameters change correctly per attempt
- Exit 42 triggers retry; exit 43 does not
- Retry profiles are progressively stricter
- Configuration files are valid
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RETRY_CONFIG = ROOT / "pipeline" / "conf" / "retry_profiles.config"
NEXTFLOW_CONFIG = ROOT / "pipeline" / "nextflow.config"
FASTP_MODULE = ROOT / "pipeline" / "modules" / "qc" / "fastp.nf"


class TestRetryProfilesConfig:
    """Test retry_profiles.config structure and values."""

    def test_config_file_exists(self):
        """retry_profiles.config exists."""
        assert RETRY_CONFIG.exists()

    def test_config_defines_three_attempts(self):
        """Config defines parameters for attempts 1, 2, and 3."""
        content = RETRY_CONFIG.read_text()
        assert "fastp_phred_1" in content
        assert "fastp_phred_2" in content
        assert "fastp_phred_3" in content

    def test_phred_scores_increase_per_attempt(self):
        """Phred quality thresholds increase with each attempt."""
        content = RETRY_CONFIG.read_text()
        phred_1 = int(re.search(r'fastp_phred_1\s*=\s*(\d+)', content).group(1))
        phred_2 = int(re.search(r'fastp_phred_2\s*=\s*(\d+)', content).group(1))
        phred_3 = int(re.search(r'fastp_phred_3\s*=\s*(\d+)', content).group(1))
        assert phred_1 < phred_2 < phred_3

    def test_length_requirements_increase_per_attempt(self):
        """Minimum length requirements increase with each attempt."""
        content = RETRY_CONFIG.read_text()
        len_1 = int(re.search(r'fastp_length_1\s*=\s*(\d+)', content).group(1))
        len_2 = int(re.search(r'fastp_length_2\s*=\s*(\d+)', content).group(1))
        len_3 = int(re.search(r'fastp_length_3\s*=\s*(\d+)', content).group(1))
        assert len_1 < len_2 < len_3

    def test_exit_42_is_retryable(self):
        """Exit code 42 is configured as retryable."""
        content = RETRY_CONFIG.read_text()
        assert "42" in content
        # Verify it's in the retryable exit codes list
        assert re.search(r'errorStrategy.*42.*retry', content, re.DOTALL)

    def test_exit_43_not_in_retry_list(self):
        """Exit code 43 is NOT in the retryable codes (hard fail)."""
        content = RETRY_CONFIG.read_text()
        error_strategy_match = re.search(
            r'errorStrategy\s*=\s*\{[^}]+\}', content
        )
        assert error_strategy_match
        strategy = error_strategy_match.group()
        # Extract the list of exit codes from the strategy
        codes_match = re.search(r'\[([^\]]+)\]', strategy)
        assert codes_match
        codes_str = codes_match.group(1)
        codes = [int(c.strip()) for c in codes_str.split(',')]
        # 43 should not be in the retryable codes
        assert 43 not in codes
        # 42 should be in there
        assert 42 in codes

    def test_max_retries_set_to_3(self):
        """FASTP process has maxRetries = 3."""
        content = RETRY_CONFIG.read_text()
        assert re.search(r'maxRetries\s*=\s*3', content)

    def test_attempt_3_enables_sliding_window(self):
        """Attempt 3 enables cut_front, cut_tail with sliding window."""
        content = RETRY_CONFIG.read_text()
        assert "fastp_cut_front_3" in content
        assert "fastp_cut_tail_3" in content
        assert "fastp_cut_window_3" in content
        assert "fastp_cut_mean_q_3" in content


class TestFastpModuleRetryAwareness:
    """Test that FASTP module uses attempt-dependent parameters."""

    def test_fastp_references_task_attempt(self):
        """FASTP module references task.attempt for parameter selection."""
        content = FASTP_MODULE.read_text()
        assert "task.attempt" in content

    def test_fastp_uses_phred_parameter(self):
        """FASTP module uses the phred parameter from retry profile."""
        content = FASTP_MODULE.read_text()
        assert "qualified_quality_phred" in content
        assert "fastp_phred_1" in content or "phred" in content

    def test_fastp_uses_length_parameter(self):
        """FASTP module uses the length parameter from retry profile."""
        content = FASTP_MODULE.read_text()
        assert "length_required" in content

    def test_fastp_supports_poly_g_trimming(self):
        """FASTP module conditionally enables poly-G trimming."""
        content = FASTP_MODULE.read_text()
        assert "trim_poly_g" in content

    def test_fastp_supports_sliding_window(self):
        """FASTP module conditionally enables cut_front/cut_tail."""
        content = FASTP_MODULE.read_text()
        assert "cut_front" in content
        assert "cut_tail" in content

    def test_fastp_has_stub_block(self):
        """FASTP module has a stub block for -stub runs."""
        content = FASTP_MODULE.read_text()
        assert "stub:" in content


class TestNextflowConfigIntegration:
    """Test that nextflow.config includes retry_profiles.config."""

    def test_includes_retry_profiles(self):
        """nextflow.config includes retry_profiles.config."""
        content = NEXTFLOW_CONFIG.read_text()
        assert "retry_profiles.config" in content

    def test_base_error_strategy_includes_standard_codes(self):
        """Base error strategy includes OOM/signal exit codes."""
        content = NEXTFLOW_CONFIG.read_text()
        for code in [143, 137, 104, 134, 139]:
            assert str(code) in content

    def test_exit_code_42_documented(self):
        """Exit code 42 is documented in retry_profiles.config."""
        content = RETRY_CONFIG.read_text()
        assert "42" in content
        # Check it's documented as QC soft fail
        assert "QC soft fail" in content or "soft fail" in content

    def test_exit_code_43_documented(self):
        """Exit code 43 is documented in retry_profiles.config."""
        content = RETRY_CONFIG.read_text()
        assert "43" in content
        # Check it's documented as QC hard fail
        assert "QC hard fail" in content or "hard fail" in content
