"""Offline intent routing for the demo pipeline assistant.

The assistant advertises example phrases to the user in two places: the help
text and the "I'm not sure how to answer that" fallback. Both shipped phrases
that silently matched nothing, so the UI was recommending dead commands.

These tests pin every advertised phrase to the intent it must route to. The
module under test is stdlib-only by design, so this runs in CI without pulling
in pandas or streamlit.
"""

from __future__ import annotations

import pytest

from demo.intents import SUGGESTED_PHRASES, match_intent


@pytest.mark.parametrize(("phrase", "expected"), sorted(SUGGESTED_PHRASES.items()))
def test_every_advertised_phrase_routes(phrase: str, expected: str) -> None:
    """A phrase the UI suggests must reach the intent it promises."""
    assert match_intent(phrase) == expected


@pytest.mark.parametrize(
    "phrase",
    [
        "compare callers",
        "Compare callers",
        "compare the callers",
        "compare caller",
        "compare gatk vs deepvariant",
        "GATK vs DeepVariant",
    ],
)
def test_caller_comparison_accepts_singular_and_plural(phrase: str) -> None:
    """The trailing \\b used to reject the plural 'callers'."""
    assert match_intent(phrase) == "compare_callers"


@pytest.mark.parametrize(
    "phrase",
    [
        "compare versions",
        "Compare versions",
        "compare the versions",
        "compare pipeline versions",
        "compare version",
    ],
)
def test_version_comparison_accepts_singular_and_plural(phrase: str) -> None:
    assert match_intent(phrase) == "version_compare"


def test_report_wins_over_sample_detail() -> None:
    """'report ... HG002' is a report request, not a sample lookup."""
    assert match_intent("Generate a report for HG002_chr20") == "report"


def test_sample_detail_without_report_keyword() -> None:
    assert match_intent("Details for HG002") == "sample_detail"


@pytest.mark.parametrize(
    "phrase",
    ["what is the weather on mars", "", "   ", "asdfghjkl"],
)
def test_unmatched_input_returns_none(phrase: str) -> None:
    """Unroutable input must fall through so the UI can show its suggestions."""
    assert match_intent(phrase) is None
