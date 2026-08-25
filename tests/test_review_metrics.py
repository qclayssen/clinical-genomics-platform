"""Tests for usage/value metrics computed over reviewer decisions (ADR-0020).

Pure-function tests (no DB) plus an end-to-end pass through the real ReviewStore
(mirrors the fixture pattern in tests/test_review_store.py).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ai-report"))

from agent.metrics import summarize_decisions  # noqa: E402
from agent.review_store import ReviewStore  # noqa: E402


@pytest.fixture
def store() -> ReviewStore:
    return ReviewStore(db_path=":memory:")


def test_summarize_empty_list():
    result = summarize_decisions([])
    assert result["total"] == 0
    assert result["approval_rate"] is None
    assert result["counts_by_decision"] == {"approved": 0, "rejected": 0}
    assert result["counts_by_classification"] == {}


def test_summarize_overall_approval_rate(store: ReviewStore):
    store.record_decision(
        run_id="demo", variant_key="chr20:1:A>G", classification="VUS",
        decision="approved", reviewer="R1",
    )
    store.record_decision(
        run_id="demo", variant_key="chr20:2:C>T", classification="VUS",
        decision="approved", reviewer="R1",
    )
    store.record_decision(
        run_id="demo", variant_key="chr20:3:G>A", classification="VUS",
        decision="rejected", reviewer="R1",
    )

    decisions = store.list_decisions()
    result = summarize_decisions(decisions)

    assert result["total"] == 3
    assert result["approval_rate"] == pytest.approx(2 / 3)
    assert result["counts_by_decision"] == {"approved": 2, "rejected": 1}


def test_summarize_by_classification(store: ReviewStore):
    store.record_decision(
        run_id="demo", variant_key="chr20:1:A>G", classification="Pathogenic",
        decision="approved", reviewer="R1",
    )
    store.record_decision(
        run_id="demo", variant_key="chr20:2:C>T", classification="Pathogenic",
        decision="rejected", reviewer="R1",
    )
    store.record_decision(
        run_id="demo", variant_key="chr20:3:G>A", classification="VUS",
        decision="approved", reviewer="R1",
    )

    decisions = store.list_decisions()
    result = summarize_decisions(decisions)

    by_class = result["counts_by_classification"]
    assert by_class["Pathogenic"] == {"approved": 1, "rejected": 1, "approval_rate": 0.5}
    assert by_class["VUS"] == {"approved": 1, "rejected": 0, "approval_rate": 1.0}


def test_summarize_single_classification_all_rejected(store: ReviewStore):
    store.record_decision(
        run_id="demo", variant_key="chr20:1:A>G", classification="Benign",
        decision="rejected", reviewer="R1",
    )

    decisions = store.list_decisions()
    result = summarize_decisions(decisions)

    assert result["approval_rate"] == 0.0
    assert result["counts_by_classification"]["Benign"]["approval_rate"] == 0.0
