"""Tests for Quarantine Logic (Soft and Hard).

Validates:
- First fail → soft quarantine
- Second consecutive fail → hard quarantine
- Successful run resets counter
- Hard quarantine blocks export/report
- Release quarantine admin action works
- Hard quarantine persists through success (requires explicit release)
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Ensure pipeline/bin is in sys.path
bin_dir = str(ROOT / "pipeline" / "bin")
if bin_dir not in sys.path:
    sys.path.insert(0, bin_dir)


def _load(module_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


quarantine_mod = _load(ROOT / "pipeline" / "bin" / "quarantine.py", "quarantine")

QuarantineManager = quarantine_mod.QuarantineManager
QuarantineStatus = quarantine_mod.QuarantineStatus
QuarantineAction = quarantine_mod.QuarantineAction


@pytest.fixture
def mgr():
    """Create a QuarantineManager with default settings."""
    return QuarantineManager(
        table_name="test-table",
        consecutive_failures_for_hard=2,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Test: First fail → soft quarantine
# ══════════════════════════════════════════════════════════════════════════════


class TestSoftQuarantine:
    """Test soft quarantine behavior on first failure."""

    def test_first_failure_evaluates_to_soft(self, mgr):
        """First failure for a clean sample → soft_quarantine action."""
        action = mgr.evaluate_failure("run-001", "HG002")
        assert action.action == "soft_quarantine"
        assert action.level == "soft"
        assert action.consecutive_failures == 1

    def test_apply_soft_quarantine_marks_sample(self, mgr):
        """apply_soft_quarantine updates internal state."""
        record = mgr.apply_soft_quarantine(
            "run-001", "HG002", reason="Duplication >20%"
        )
        status = mgr.check_quarantine_status("HG002")
        assert status.is_quarantined is True
        assert status.level == "soft"
        assert status.consecutive_failures == 1

    def test_soft_quarantine_record_structure(self, mgr):
        """Soft quarantine record has all required fields."""
        record = mgr.apply_soft_quarantine(
            "run-001",
            "HG002",
            reason="F1 below threshold",
            detail={"snp_f1": 0.993, "threshold": 0.995},
        )
        assert record["record_type"] == "QUARANTINE"
        assert record["sample_id"] == "HG002"
        assert record["level"] == "soft"
        assert record["triggering_run_id"] == "run-001"
        assert record["reason"] == "F1 below threshold"
        assert record["released"] is False
        assert "created_at" in record

    def test_soft_quarantine_blocks_report(self, mgr):
        """Soft quarantine blocks report generation."""
        mgr.apply_soft_quarantine("run-001", "HG002")
        assert mgr.is_blocked_for_report("HG002") is True

    def test_clean_sample_not_blocked(self, mgr):
        """A clean sample is not blocked."""
        assert mgr.is_blocked_for_report("HG003") is False
        assert mgr.is_blocked_for_export("HG003") is False


# ══════════════════════════════════════════════════════════════════════════════
# Test: Second consecutive fail → hard quarantine
# ══════════════════════════════════════════════════════════════════════════════


class TestHardQuarantine:
    """Test hard quarantine escalation on consecutive failures."""

    def test_second_consecutive_failure_evaluates_to_hard(self, mgr):
        """Second consecutive failure → hard_quarantine action."""
        mgr.apply_soft_quarantine("run-001", "HG002")
        action = mgr.evaluate_failure("run-002", "HG002")
        assert action.action == "hard_quarantine"
        assert action.level == "hard"
        assert action.consecutive_failures == 2

    def test_apply_hard_quarantine_marks_sample(self, mgr):
        """apply_hard_quarantine updates state to hard level."""
        mgr.apply_soft_quarantine("run-001", "HG002")
        record = mgr.apply_hard_quarantine("run-002", "HG002", reason="Consecutive failures")
        status = mgr.check_quarantine_status("HG002")
        assert status.is_quarantined is True
        assert status.level == "hard"
        assert status.consecutive_failures == 2

    def test_hard_quarantine_record_has_prefix(self, mgr):
        """Hard quarantine record includes quarantined prefix."""
        mgr.apply_soft_quarantine("run-001", "HG002")
        record = mgr.apply_hard_quarantine("run-002", "HG002")
        assert "quarantined_prefix" in record
        assert record["quarantined_prefix"].startswith("quarantined/")

    def test_hard_quarantine_blocks_export(self, mgr):
        """Hard quarantine blocks export."""
        mgr.apply_soft_quarantine("run-001", "HG002")
        mgr.apply_hard_quarantine("run-002", "HG002")
        assert mgr.is_blocked_for_export("HG002") is True
        assert mgr.is_blocked_for_report("HG002") is True

    def test_already_hard_quarantined_returns_already(self, mgr):
        """Subsequent failure on hard-quarantined sample returns already_quarantined."""
        mgr.apply_soft_quarantine("run-001", "HG002")
        mgr.apply_hard_quarantine("run-002", "HG002")
        action = mgr.evaluate_failure("run-003", "HG002")
        assert action.action == "already_quarantined"


# ══════════════════════════════════════════════════════════════════════════════
# Test: Successful run resets counter
# ══════════════════════════════════════════════════════════════════════════════


class TestSuccessResets:
    """Test that successful runs reset the failure counter."""

    def test_success_after_soft_quarantine_clears(self, mgr):
        """A successful run after soft quarantine clears the state."""
        mgr.apply_soft_quarantine("run-001", "HG002")
        mgr.record_success("run-002", "HG002")
        status = mgr.check_quarantine_status("HG002")
        assert status.is_quarantined is False
        assert status.level == "none"
        assert status.consecutive_failures == 0

    def test_success_resets_failure_counter(self, mgr):
        """After success, next failure starts fresh at count=1."""
        mgr.apply_soft_quarantine("run-001", "HG002")
        mgr.record_success("run-002", "HG002")
        action = mgr.evaluate_failure("run-003", "HG002")
        assert action.action == "soft_quarantine"
        assert action.consecutive_failures == 1

    def test_success_does_not_clear_hard_quarantine(self, mgr):
        """Hard quarantine persists through successful runs."""
        mgr.apply_soft_quarantine("run-001", "HG002")
        mgr.apply_hard_quarantine("run-002", "HG002")
        mgr.record_success("run-003", "HG002")
        status = mgr.check_quarantine_status("HG002")
        assert status.level == "hard"
        assert mgr.is_blocked_for_export("HG002") is True


# ══════════════════════════════════════════════════════════════════════════════
# Test: Release quarantine admin action
# ══════════════════════════════════════════════════════════════════════════════


class TestReleaseQuarantine:
    """Test quarantine release admin action."""

    def test_release_clears_soft_quarantine(self, mgr):
        """release_quarantine clears soft quarantine."""
        mgr.apply_soft_quarantine("run-001", "HG002")
        record = mgr.release_quarantine("HG002", released_by="admin", reason="Manual review OK")
        status = mgr.check_quarantine_status("HG002")
        assert status.is_quarantined is False
        assert status.level == "none"

    def test_release_clears_hard_quarantine(self, mgr):
        """release_quarantine clears hard quarantine."""
        mgr.apply_soft_quarantine("run-001", "HG002")
        mgr.apply_hard_quarantine("run-002", "HG002")
        record = mgr.release_quarantine("HG002", released_by="operator", reason="Reprocessed")
        status = mgr.check_quarantine_status("HG002")
        assert status.is_quarantined is False
        assert status.level == "none"

    def test_release_produces_audit_record(self, mgr):
        """release_quarantine returns an AUDIT record."""
        mgr.apply_soft_quarantine("run-001", "HG002")
        record = mgr.release_quarantine("HG002", released_by="admin", reason="Fixed")
        assert record["record_type"] == "AUDIT"
        assert record["action"] == "QUARANTINE_RELEASED"
        assert record["detail"]["released_by"] == "admin"
        assert record["detail"]["previous_level"] == "soft"

    def test_release_nonexistent_is_safe(self, mgr):
        """Releasing a non-quarantined sample is a no-op."""
        record = mgr.release_quarantine("HG999", released_by="admin", reason="Cleanup")
        assert record["action"] == "QUARANTINE_RELEASED"
        assert record["detail"]["previous_level"] == "none"


# ══════════════════════════════════════════════════════════════════════════════
# Test: Multiple samples independent
# ══════════════════════════════════════════════════════════════════════════════


class TestMultipleSamples:
    """Test that quarantine state is per-sample."""

    def test_different_samples_independent(self, mgr):
        """Quarantine state for one sample doesn't affect another."""
        mgr.apply_soft_quarantine("run-001", "HG002")
        assert mgr.is_blocked_for_report("HG002") is True
        assert mgr.is_blocked_for_report("HG003") is False

    def test_different_samples_escalate_independently(self, mgr):
        """Each sample tracks its own consecutive failures."""
        mgr.apply_soft_quarantine("run-001", "HG002")
        mgr.apply_soft_quarantine("run-002", "HG003")
        # HG002 second failure → hard
        action = mgr.evaluate_failure("run-003", "HG002")
        assert action.action == "hard_quarantine"
        # HG003 second failure → also hard
        action = mgr.evaluate_failure("run-004", "HG003")
        assert action.action == "hard_quarantine"
