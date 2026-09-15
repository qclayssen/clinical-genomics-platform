"""Single source of truth for AI-output guardrails (ADR-0008).

Before this module existed, the "strip the model's untrusted output down to
something a clinician can safely read" logic had drifted into two shapes:

- `ai-report/infer.py` and `lambdas/report_generator/handler.py` each carried
  their own `enforce_guardrails()`, scrubbing only 3 advice-phrase patterns.
- `ai-report/agent/react.py` carried a separate `enforce_safety_constraints()`
  scrubbing 8 patterns, for the ReAct agent's per-variant interpretation
  summaries rather than a full metrics.json-driven report.

See docs/FIXES-TODO.md's "Two divergent copies of enforce_guardrails()" entry.
Both flavors now share the one canonical pattern list and scrub routine here:

- `enforce_guardrails(text, metrics)` — for a full AI-drafted report: adds the
  mandatory review banner and a `Provenance:` line if the model dropped them,
  then scrubs advice language. Used by `ai-report/infer.py` and
  `lambdas/report_generator/handler.py`.
- `enforce_safety_constraints(text)` — for a smaller fragment (a single
  variant's interpretation summary) that already lives inside a larger,
  separately-guardrailed report (see `ai-report/agent/report.py`'s
  `INTERPRETATION_BANNER`). No banner/provenance injection here; it just
  scrubs and reports what it found, for the caller's audit trace. Used by
  `ai-report/agent/react.py`.

Do not fork this file again. If a call site needs different behaviour, add a
parameter or a thin wrapper here — not a copy of the pattern list.
"""
from __future__ import annotations

import re

# Mandatory review banner (ADR-0008). Every AI-drafted report must carry this,
# verbatim, before a human ever sees it.
BANNER = "AI-DRAFTED — REQUIRES CLINICIAN REVIEW"

# Canonical advice/treatment/diagnosis phrase list. This is the union of what
# used to be two divergent lists: the narrower 3-pattern list scrubbed
# "we recommend", "diagnos*", and "treat* with"; the ReAct agent's 8-pattern
# list additionally caught "should start/stop/...", prescriptions, therapy,
# medication, and "clinical management". Kept broad (not narrowed) on merge
# so neither call site regresses.
ADVICE_PATTERNS = [
    r"\bwe recommend\b",
    r"\bshould (?:take|start|stop|begin|consider)\b",
    r"\btreat(?:ment|ed|ing)?\s*with\b",
    r"\bprescri(?:be|bed|ption)\b",
    r"\bdiagnos\w+\b",
    r"\btherapy\b",
    r"\bmedication\b",
    r"\bclinical management\b",
]

_ADVICE_RE = re.compile("|".join(ADVICE_PATTERNS), re.IGNORECASE)


def scrub_advice_language(text: str, replacement: str = "[review required]") -> tuple[str, list[str]]:
    """Strip hallucinated clinical-recommendation/treatment phrasing.

    Returns ``(scrubbed_text, raw_matches)`` so callers that need to log what
    was removed (e.g. the ReAct agent's reasoning trace) can do so.
    """
    matches = _ADVICE_RE.findall(text)
    scrubbed = _ADVICE_RE.sub(replacement, text)
    return scrubbed, matches


def enforce_guardrails(text: str, metrics: dict) -> str:
    """Guarantee the review banner, provenance line, and advice scrub survive
    in a full AI-drafted report.

    The model output is untrusted: this re-inserts the banner/provenance if
    the model dropped them, and scrubs advice language either way.
    """
    if BANNER not in text:
        text = BANNER + "\n\n" + text
    prov = metrics.get("provenance", {})
    if "Provenance:" not in text:
        text += (
            f"\n\nProvenance: git {prov.get('git_commit', '?')}, "
            f"{prov.get('truth_version', '?')}."
        )
    text, _ = scrub_advice_language(text)
    return text


def enforce_safety_constraints(text: str) -> tuple[str, list[str]]:
    """Enforce clinical safety constraints on a variant-interpretation summary.

    Unlike `enforce_guardrails()`, this does not inject a banner or provenance
    line — it operates on a fragment (one variant's summary) that lives inside
    a larger report already guardrailed elsewhere. Returns
    ``(scrubbed_text, violations)`` where `violations` is a human-readable list
    describing what was found, for the caller's audit trace.
    """
    scrubbed, matches = scrub_advice_language(text, replacement="[REVIEW REQUIRED]")
    violations = [f"Treatment language detected: {matches}"] if matches else []
    return scrubbed, violations
