"""Intent routing for the offline pipeline assistant.

Split out of ``chat.py`` so the routing rules can be unit-tested without
importing streamlit or pandas — CI installs neither, so rules living next to
the UI code were untestable and shipped broken.

``chat.py`` owns the tool implementations (they need a DataFrame); this module
owns only the question -> intent decision.
"""

from __future__ import annotations

import re

# Trailing \b after an alternation rejects plurals: "caller\b" does not match
# "callers". Use an optional "s" so both forms route.
INTENTS: list[tuple[re.Pattern, str, dict]] = [
    (re.compile(r"\b(summary|overview|overall|how many|status)\b", re.I), "summary", {}),
    (re.compile(r"\b(best|highest|top).*(f1|score|precision)\b", re.I), "best_f1", {}),
    (re.compile(r"\b(worst|lowest|bottom).*(f1|score)\b", re.I), "worst_f1", {}),
    (re.compile(r"\b(fail|failed|failures|didn.t pass)\b", re.I), "failures", {}),
    (
        re.compile(r"\b(compare|vs|versus).*\b(caller|gatk|deepvariant)s?\b", re.I),
        "compare_callers",
        {},
    ),
    (
        re.compile(r"\b(compare|vs|versus).*\b(version|pipeline)s?\b", re.I),
        "version_compare",
        {},
    ),
    (
        re.compile(r"\b(version|pipeline)s?\b.*\b(compare|vs|versus)\b", re.I),
        "version_compare",
        {},
    ),
    (re.compile(r"\b(last|recent|latest)\s*(\d+)?\s*(run)?\b", re.I), "last_n_runs", {}),
    (re.compile(r"\b(dup|duplication)\b", re.I), "duplication", {}),
    (re.compile(r"\b(help|what can you|commands|capabilities)\b", re.I), "help", {}),
]

SAMPLE_PATTERN = re.compile(r"\b(detail|show|info|about|for)\b.*\b(HG\d+|NA\d+)\w*", re.I)
SAMPLE_EXTRACT = re.compile(r"\b(HG\d+\w*|NA\d+\w*)", re.I)
REPORT_PATTERN = re.compile(
    r"\b(report|generate|draft|summarize|summarise)\b.*\b(HG\d+|NA\d+)\w*", re.I
)

# Every phrase the UI offers the user, mapped to the intent it must reach.
# tests/test_demo_chat.py asserts each one still routes, so a suggestion can
# never go dead again. Keep in sync with _tool_help() and the fallback message.
SUGGESTED_PHRASES: dict[str, str] = {
    # Shown by _tool_help()
    "What's the overall summary?": "summary",
    "Are there any failures?": "failures",
    "Show the last 5 runs": "last_n_runs",
    "Compare GATK vs DeepVariant": "compare_callers",
    "Compare pipeline versions": "version_compare",
    "Show me details for HG002": "sample_detail",
    "What are the duplication rates?": "duplication",
    "Which run had the best F1?": "best_f1",
    "Generate a report for HG002_chr20": "report",
    # Shown by the "not sure how to answer" fallback
    "Compare callers": "compare_callers",
    "Compare versions": "version_compare",
    "Show failures": "failures",
    "Show duplication rates": "duplication",
    "Details for HG002": "sample_detail",
}


def match_intent(user_msg: str) -> str | None:
    """Route a message to an intent key, or None if nothing matches.

    Order matters: a report request mentioning a sample ("generate a report for
    HG002") is a report, not a sample lookup, so REPORT_PATTERN is checked
    first. Returns the key only — callers extract sample names themselves.
    """
    if REPORT_PATTERN.search(user_msg):
        return "report"

    if SAMPLE_PATTERN.search(user_msg) and SAMPLE_EXTRACT.search(user_msg):
        return "sample_detail"

    for pattern, intent_key, _extra in INTENTS:
        if pattern.search(user_msg):
            return intent_key

    # A bare sample name ("HG002?") is still a sample lookup.
    if SAMPLE_EXTRACT.search(user_msg):
        return "sample_detail"

    return None
