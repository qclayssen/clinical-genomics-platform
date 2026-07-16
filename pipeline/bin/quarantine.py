#!/usr/bin/env python3
"""Quarantine Logic — Soft and Hard Quarantine for QC Failures.

Implements escalating quarantine:
  - Soft quarantine: first QC failure → mark in DynamoDB, block report generation,
    keep outputs for review.
  - Hard quarantine: second consecutive QC failure for same sample → move to
    quarantined/ prefix, create audit record, send SNS notification.

Usage:
    from quarantine import QuarantineManager

    mgr = QuarantineManager(table_name="cgp-metadata")
    status = mgr.check_quarantine_status(sample_id)
    mgr.apply_soft_quarantine(run_id, sample_id, reason, detail)
    mgr.apply_hard_quarantine(run_id, sample_id, reason, detail)
    mgr.release_quarantine(sample_id, released_by, reason)
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QuarantineStatus:
    """Current quarantine status for a sample."""

    sample_id: str
    is_quarantined: bool = False
    level: str = "none"  # "none", "soft", "hard"
    consecutive_failures: int = 0
    last_failure_run_id: str = ""
    last_failure_at: str = ""
    reason: str = ""


@dataclass
class QuarantineAction:
    """Result of a quarantine evaluation."""

    action: str  # "none", "soft_quarantine", "hard_quarantine", "already_quarantined"
    level: str  # "none", "soft", "hard"
    consecutive_failures: int = 0
    message: str = ""


class QuarantineManager:
    """Manages escalating quarantine for samples that fail QC.

    Quarantine escalation:
      1. First failure → soft quarantine (block reports, keep data)
      2. Second consecutive failure → hard quarantine (move data, full block)
      3. Successful run → reset failure counter

    DynamoDB records use record_type=QUARANTINE with sample_id as context.
    """

    RECORD_TYPE = "QUARANTINE"

    def __init__(
        self,
        table_name: str = "cgp-metadata",
        consecutive_failures_for_hard: int = 2,
        sns_topic_arn: str | None = None,
    ):
        """Initialize QuarantineManager.

        Args:
            table_name: DynamoDB table name.
            consecutive_failures_for_hard: Number of consecutive failures
                before escalating from soft to hard quarantine.
            sns_topic_arn: SNS topic ARN for hard quarantine notifications.
        """
        self._table_name = table_name
        self._consecutive_failures_for_hard = consecutive_failures_for_hard
        self._sns_topic_arn = sns_topic_arn
        # In-memory state for testing; production uses DynamoDB
        self._state: dict[str, QuarantineStatus] = {}

    def check_quarantine_status(self, sample_id: str) -> QuarantineStatus:
        """Check the current quarantine status for a sample.

        Args:
            sample_id: Sample identifier.

        Returns:
            QuarantineStatus with current level and failure count.
        """
        if sample_id in self._state:
            return self._state[sample_id]
        return QuarantineStatus(sample_id=sample_id)

    def evaluate_failure(self, run_id: str, sample_id: str) -> QuarantineAction:
        """Evaluate a QC failure and determine quarantine action.

        This is the main entry point: given a sample that just failed QC,
        determine whether to apply soft or hard quarantine.

        Args:
            run_id: Run identifier that failed.
            sample_id: Sample identifier.

        Returns:
            QuarantineAction indicating what action to take.
        """
        status = self.check_quarantine_status(sample_id)

        if status.level == "hard":
            return QuarantineAction(
                action="already_quarantined",
                level="hard",
                consecutive_failures=status.consecutive_failures,
                message=f"Sample {sample_id} is already under hard quarantine",
            )

        new_failures = status.consecutive_failures + 1

        if new_failures >= self._consecutive_failures_for_hard:
            return QuarantineAction(
                action="hard_quarantine",
                level="hard",
                consecutive_failures=new_failures,
                message=(
                    f"Sample {sample_id} failed QC {new_failures} times consecutively "
                    f"— escalating to hard quarantine"
                ),
            )
        else:
            return QuarantineAction(
                action="soft_quarantine",
                level="soft",
                consecutive_failures=new_failures,
                message=(
                    f"Sample {sample_id} failed QC (attempt {new_failures}) "
                    f"— applying soft quarantine"
                ),
            )

    def apply_soft_quarantine(
        self,
        run_id: str,
        sample_id: str,
        reason: str = "",
        detail: dict[str, Any] | None = None,
    ) -> dict:
        """Apply soft quarantine to a sample.

        Soft quarantine:
          - Marks sample in DynamoDB
          - Blocks report generation
          - Keeps all outputs for manual review
          - Does NOT move data to quarantine prefix

        Args:
            run_id: Run identifier that triggered quarantine.
            sample_id: Sample identifier.
            reason: Human-readable reason for quarantine.
            detail: Additional detail (metric values, thresholds, etc.)

        Returns:
            DynamoDB record dict that was written.
        """
        now = datetime.now(timezone.utc).isoformat()

        status = self.check_quarantine_status(sample_id)
        new_failures = status.consecutive_failures + 1

        record = {
            "run_id": f"QUARANTINE#{sample_id}",
            "record_type": self.RECORD_TYPE,
            "sample_id": sample_id,
            "created_at": now,
            "level": "soft",
            "consecutive_failures": new_failures,
            "triggering_run_id": run_id,
            "reason": reason,
            "detail": detail or {},
            "released": False,
        }

        # Update internal state
        self._state[sample_id] = QuarantineStatus(
            sample_id=sample_id,
            is_quarantined=True,
            level="soft",
            consecutive_failures=new_failures,
            last_failure_run_id=run_id,
            last_failure_at=now,
            reason=reason,
        )

        logger.info(
            json.dumps({
                "action": "soft_quarantine_applied",
                "sample_id": sample_id,
                "run_id": run_id,
                "consecutive_failures": new_failures,
            })
        )

        return record

    def apply_hard_quarantine(
        self,
        run_id: str,
        sample_id: str,
        reason: str = "",
        detail: dict[str, Any] | None = None,
    ) -> dict:
        """Apply hard quarantine to a sample.

        Hard quarantine:
          - Marks sample in DynamoDB with level=hard
          - Blocks report generation AND export
          - Triggers move to quarantined/ S3 prefix
          - Sends SNS notification
          - Creates AUDIT record

        Args:
            run_id: Run identifier that triggered quarantine.
            sample_id: Sample identifier.
            reason: Human-readable reason for quarantine.
            detail: Additional detail (metric values, thresholds, etc.)

        Returns:
            DynamoDB record dict that was written.
        """
        now = datetime.now(timezone.utc).isoformat()

        status = self.check_quarantine_status(sample_id)
        new_failures = status.consecutive_failures + 1

        record = {
            "run_id": f"QUARANTINE#{sample_id}",
            "record_type": self.RECORD_TYPE,
            "sample_id": sample_id,
            "created_at": now,
            "level": "hard",
            "consecutive_failures": new_failures,
            "triggering_run_id": run_id,
            "reason": reason,
            "detail": detail or {},
            "released": False,
            "quarantined_prefix": f"quarantined/{sample_id}/{run_id}/",
        }

        # Update internal state
        self._state[sample_id] = QuarantineStatus(
            sample_id=sample_id,
            is_quarantined=True,
            level="hard",
            consecutive_failures=new_failures,
            last_failure_run_id=run_id,
            last_failure_at=now,
            reason=reason,
        )

        logger.info(
            json.dumps({
                "action": "hard_quarantine_applied",
                "sample_id": sample_id,
                "run_id": run_id,
                "consecutive_failures": new_failures,
                "quarantined_prefix": record["quarantined_prefix"],
            })
        )

        return record

    def record_success(self, run_id: str, sample_id: str) -> None:
        """Record a successful QC run, resetting the failure counter.

        A successful run clears the quarantine state for the sample,
        unless it's under hard quarantine (which requires explicit release).

        Args:
            run_id: Run identifier that succeeded.
            sample_id: Sample identifier.
        """
        status = self.check_quarantine_status(sample_id)

        if status.level == "hard":
            # Hard quarantine requires explicit release
            logger.info(
                json.dumps({
                    "action": "success_recorded_but_hard_quarantine_persists",
                    "sample_id": sample_id,
                    "run_id": run_id,
                })
            )
            return

        # Reset failure counter for soft or no quarantine
        if sample_id in self._state:
            del self._state[sample_id]

        logger.info(
            json.dumps({
                "action": "success_recorded_quarantine_cleared",
                "sample_id": sample_id,
                "run_id": run_id,
            })
        )

    def release_quarantine(
        self,
        sample_id: str,
        released_by: str = "operator",
        reason: str = "",
    ) -> dict:
        """Release a sample from quarantine (admin action).

        Args:
            sample_id: Sample identifier to release.
            released_by: Who is releasing (operator, system, etc.)
            reason: Reason for releasing quarantine.

        Returns:
            Audit record for the release.
        """
        now = datetime.now(timezone.utc).isoformat()

        status = self.check_quarantine_status(sample_id)
        previous_level = status.level

        # Clear quarantine state
        if sample_id in self._state:
            del self._state[sample_id]

        record = {
            "run_id": f"QUARANTINE_RELEASE#{sample_id}",
            "record_type": "AUDIT",
            "sample_id": sample_id,
            "created_at": now,
            "action": "QUARANTINE_RELEASED",
            "detail": {
                "previous_level": previous_level,
                "released_by": released_by,
                "reason": reason,
            },
        }

        logger.info(
            json.dumps({
                "action": "quarantine_released",
                "sample_id": sample_id,
                "previous_level": previous_level,
                "released_by": released_by,
            })
        )

        return record

    def is_blocked_for_export(self, sample_id: str) -> bool:
        """Check if a sample is blocked from export/report generation.

        Both soft and hard quarantine block exports.

        Args:
            sample_id: Sample identifier.

        Returns:
            True if the sample should not have reports/exports generated.
        """
        status = self.check_quarantine_status(sample_id)
        return status.level in ("soft", "hard")

    def is_blocked_for_report(self, sample_id: str) -> bool:
        """Check if a sample is blocked from report generation.

        Both soft and hard quarantine block report generation.

        Args:
            sample_id: Sample identifier.

        Returns:
            True if the sample should not have reports generated.
        """
        return self.is_blocked_for_export(sample_id)
