"""build_report() scrubs advice language out of each summary — but used to
throw away *what* it scrubbed, and enforce_report_guardrails() then re-checked
the already-clean text, so /agent/variant-review returned an empty
guardrail_violations list for a summary it had just rewritten."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ai-report"))

from agent.deterministic import DeterministicInterpreter  # noqa: E402
from agent.react import Variant  # noqa: E402
from agent.report import build_report, enforce_report_guardrails  # noqa: E402


def test_scrubbed_summary_violations_reach_the_report_check():
    result = DeterministicInterpreter().run(Variant(chrom="chr20", pos=4699605, ref="G", alt="A", gene="PRNP"))
    result.summary = "Likely pathogenic. We recommend treatment with doxycycline."

    report = build_report([result], backend_used="deterministic", run_id="t")

    assert "We recommend" not in report.variants[0].summary  # still scrubbed
    violations = enforce_report_guardrails(report)
    assert any("Treatment language" in v for v in violations), violations


def test_clean_summary_reports_no_scrub_violation():
    result = DeterministicInterpreter().run(Variant(chrom="chr20", pos=4699605, ref="G", alt="A", gene="PRNP"))
    report = build_report([result], backend_used="deterministic", run_id="t")
    assert not any("Treatment language" in v for v in enforce_report_guardrails(report))
