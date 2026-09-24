"""Tests for the shared AI-output guardrails module (ai-report/guardrails.py).

Before this module existed, `ai-report/infer.py` and
`lambdas/report_generator/handler.py` each carried their own 3-pattern
`enforce_guardrails()`, while `ai-report/agent/react.py` carried a separate
8-pattern `enforce_safety_constraints()` — see docs/FIXES-TODO.md's "Two
divergent copies of enforce_guardrails()" entry (now closed).

This file:
  1. Exercises the canonical scrub/banner/provenance logic directly, for all
     8 advice-phrase categories (not just the 3 the old infer.py copy
     covered).
  2. Pins each of the three call sites to the *same* function object, so a
     future accidental re-fork (copy-pasting the logic back into a call site
     instead of importing it) fails CI immediately.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_AI_REPORT_DIR = ROOT / "ai-report"
if str(_AI_REPORT_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_REPORT_DIR))

import guardrails  # noqa: E402

SAMPLE_METRICS = {
    "sample": "HG002_chr20",
    "validation_pass": True,
    "provenance": {
        "caller": "gatk",
        "git_commit": "abc1234",
        "truth_version": "GIAB-v4.2.1",
        "n_variants": 61000,
    },
}


# ═══ enforce_guardrails() — full report guardrail ═══


def test_enforce_guardrails_adds_missing_banner_and_provenance():
    result = guardrails.enforce_guardrails("Plain model output.", SAMPLE_METRICS)
    assert result.startswith(guardrails.BANNER)
    assert "Provenance: git abc1234, GIAB-v4.2.1." in result


def test_enforce_guardrails_does_not_duplicate_existing_banner_or_provenance():
    text = f"{guardrails.BANNER}\n\nBody.\n\nProvenance: git abc1234, GIAB-v4.2.1."
    result = guardrails.enforce_guardrails(text, SAMPLE_METRICS)
    assert result.count(guardrails.BANNER) == 1
    assert result.count("Provenance:") == 1


def test_enforce_guardrails_banner_is_first_even_if_model_embeds_it():
    # The model is untrusted: echoing the banner mid-text must not stand in
    # for the real one at the top of the report.
    text = f"Body first.\n(not {guardrails.BANNER})"
    result = guardrails.enforce_guardrails(text, SAMPLE_METRICS)
    assert result.startswith(guardrails.BANNER)
    assert result.count(guardrails.BANNER) == 1


def test_enforce_guardrails_replaces_model_forged_provenance():
    text = "Body.\nProvenance: none."
    result = guardrails.enforce_guardrails(text, SAMPLE_METRICS)
    assert "Provenance: none." not in result
    assert result.rstrip().endswith("Provenance: git abc1234, GIAB-v4.2.1.")
    assert result.count("Provenance:") == 1


def test_enforce_guardrails_tolerates_null_provenance():
    result = guardrails.enforce_guardrails("Body.", {"provenance": None})
    assert "Provenance: git ?, ?." in result


def test_enforce_guardrails_scrubs_first_person_and_receive_phrasing():
    text = "Patient should receive tamoxifen; I recommend confirmatory testing."
    result = guardrails.enforce_guardrails(text, SAMPLE_METRICS)
    assert "should receive" not in result.lower()
    assert "i recommend" not in result.lower()


# ═══ Advice-phrase scrub: all 8 canonical categories ═══
# (the earlier infer.py/handler.py copy only scrubbed the first 3 of these)

ADVICE_EXAMPLES = [
    "We recommend further testing.",
    "The patient should start a new medication regimen.",
    "This should be treated with antibiotics.",
    "Please prescribe amoxicillin.",
    "This diagnosis is confirmed by the variant.",
    "Consider gene therapy as an option.",
    "Adjust the medication dosage.",
    "Refer to clinical management guidelines.",
]


def test_scrub_advice_language_strips_all_eight_categories():
    for phrase in ADVICE_EXAMPLES:
        scrubbed, matches = guardrails.scrub_advice_language(phrase)
        assert matches, f"expected a match for: {phrase!r}"
        assert not guardrails._ADVICE_RE.search(scrubbed), (
            f"advice language survived scrubbing: {phrase!r} -> {scrubbed!r}"
        )


def test_enforce_guardrails_scrubs_hostile_model_output():
    hostile = "Sample looks great. We recommend treatment with drug X."
    fixed = guardrails.enforce_guardrails(hostile, SAMPLE_METRICS)
    assert fixed.startswith(guardrails.BANNER)
    assert "recommend" not in fixed.lower()
    assert "Provenance:" in fixed


# ═══ enforce_safety_constraints() — per-variant summary guardrail ═══


def test_enforce_safety_constraints_scrubs_and_reports_violations():
    text = "We recommend starting therapy immediately."
    scrubbed, violations = guardrails.enforce_safety_constraints(text)
    assert "[REVIEW REQUIRED]" in scrubbed
    assert violations, "expected at least one violation to be reported"
    assert "Treatment language detected" in violations[0]


def test_enforce_safety_constraints_no_banner_or_provenance_injected():
    """Unlike enforce_guardrails(), this operates on a report fragment and
    must not inject a banner/provenance line of its own."""
    text = "This variant is benign."
    scrubbed, violations = guardrails.enforce_safety_constraints(text)
    assert scrubbed == text
    assert violations == []
    assert guardrails.BANNER not in scrubbed
    assert "Provenance:" not in scrubbed


# ═══ Call-site pinning: catch a future re-fork immediately ═══


def test_infer_py_calls_the_shared_implementation():
    infer = _load_infer()
    assert infer.enforce_guardrails is guardrails.enforce_guardrails
    assert infer.BANNER == guardrails.BANNER


def test_react_py_calls_the_shared_implementation():
    if str(_AI_REPORT_DIR) not in sys.path:
        sys.path.insert(0, str(_AI_REPORT_DIR))
    from agent import react

    assert react.enforce_safety_constraints is guardrails.enforce_safety_constraints


def test_report_generator_handler_calls_the_shared_implementation():
    from lambdas.report_generator import handler

    assert handler.enforce_guardrails is guardrails.enforce_guardrails
    assert handler.BANNER == guardrails.BANNER


def _load_infer():
    import importlib.util

    spec = importlib.util.spec_from_file_location("infer", _AI_REPORT_DIR / "infer.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
