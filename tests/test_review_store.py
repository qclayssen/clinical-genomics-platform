"""Tests for the insert-only reviewer decision log (ADR-0019).

Requires no network, no GPU, no Postgres — the store is pure SQLite.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ai-report"))

from agent.review_store import ReviewStore, variant_key  # noqa: E402


@pytest.fixture
def store() -> ReviewStore:
    return ReviewStore(db_path=":memory:")


def test_variant_key_format():
    assert variant_key("chr20", 123456, "A", "G") == "chr20:123456:A>G"


def test_record_and_list_decision(store: ReviewStore):
    row_id = store.record_decision(
        run_id="demo",
        variant_key="chr20:123456:A>G",
        classification="Likely Pathogenic",
        decision="approved",
        reviewer="Dr. Smith",
        comment="Concordant with ClinVar.",
    )
    assert row_id == 1

    decisions = store.list_decisions(variant_key="chr20:123456:A>G")
    assert len(decisions) == 1
    d = decisions[0]
    assert d.reviewer == "Dr. Smith"
    assert d.decision == "approved"
    assert d.classification == "Likely Pathogenic"


def test_list_decisions_newest_first(store: ReviewStore):
    store.record_decision(
        run_id="demo", variant_key="chr20:1:A>G", classification="VUS",
        decision="rejected", reviewer="Reviewer A",
    )
    store.record_decision(
        run_id="demo", variant_key="chr20:1:A>G", classification="VUS",
        decision="approved", reviewer="Reviewer B",
    )
    decisions = store.list_decisions(variant_key="chr20:1:A>G")
    assert [d.reviewer for d in decisions] == ["Reviewer B", "Reviewer A"]


def test_filter_by_run_id(store: ReviewStore):
    store.record_decision(
        run_id="run_a", variant_key="chr20:1:A>G", classification="VUS",
        decision="approved", reviewer="R",
    )
    store.record_decision(
        run_id="run_b", variant_key="chr20:2:C>T", classification="VUS",
        decision="approved", reviewer="R",
    )
    assert len(store.list_decisions(run_id="run_a")) == 1
    assert len(store.list_decisions(run_id="run_b")) == 1


def test_rejects_invalid_decision(store: ReviewStore):
    with pytest.raises(ValueError):
        store.record_decision(
            run_id="demo", variant_key="chr20:1:A>G", classification="VUS",
            decision="maybe", reviewer="R",
        )


def test_rejects_blank_reviewer(store: ReviewStore):
    with pytest.raises(ValueError):
        store.record_decision(
            run_id="demo", variant_key="chr20:1:A>G", classification="VUS",
            decision="approved", reviewer="   ",
        )


def test_no_mutation_methods_exposed(store: ReviewStore):
    """Insert-only by construction: there is nothing to call to edit a row."""
    assert not hasattr(store, "update_decision")
    assert not hasattr(store, "delete_decision")
