"""Pure functions for usage/value metrics over reviewer decisions.

Takes the same `ReviewDecision` rows `review_store.ReviewStore.list_decisions()` returns and
computes the numbers documented in `docs/METRICS.md`. No database access here — this mirrors
the SQL in that doc for the SQLite/demo path and for unit testing without a DB.

See ADR-0020.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.review_store import ReviewDecision


def summarize_decisions(decisions: list["ReviewDecision"]) -> dict:
    """Return approval rate, decision counts, and per-classification counts.

    {
        "total": int,
        "approval_rate": float | None,      # None if there are no decisions at all
        "counts_by_decision": {"approved": int, "rejected": int},
        "counts_by_classification": {
            "<classification>": {"approved": int, "rejected": int, "approval_rate": float | None},
            ...
        },
    }
    """
    counts_by_decision = Counter(d.decision for d in decisions)
    approved = counts_by_decision.get("approved", 0)
    rejected = counts_by_decision.get("rejected", 0)
    total = approved + rejected

    by_classification: dict[str, dict] = {}
    for d in decisions:
        bucket = by_classification.setdefault(
            d.classification, {"approved": 0, "rejected": 0}
        )
        bucket[d.decision] = bucket.get(d.decision, 0) + 1

    for bucket in by_classification.values():
        bucket_total = bucket.get("approved", 0) + bucket.get("rejected", 0)
        bucket["approval_rate"] = (
            bucket.get("approved", 0) / bucket_total if bucket_total else None
        )

    return {
        "total": total,
        "approval_rate": approved / total if total else None,
        "counts_by_decision": {"approved": approved, "rejected": rejected},
        "counts_by_classification": by_classification,
    }
