"""End-to-end smoke tests for the variant interpretation agent.

Runs the full agent pipeline with the DeterministicBackend on fixture data,
verifying that:
  - Report is generated with correct structure
  - Guardrails are enforced (banner, VUS flag, provenance)
  - Agent trace is recorded with expected tool calls
  - CLI produces valid output and exit codes

These tests require NO network access, NO GPU, and NO LLM — they use the
deterministic backend exclusively, making them safe for CI.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Add ai-report to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ai-report"))

from agent.deterministic import DeterministicInterpreter
from agent.llm import DeterministicBackend
from agent.react import ReActAgent, Variant
from agent.report import (
    INTERPRETATION_BANNER,
    VUS_UNCERTAINTY_STATEMENT,
    build_report,
    enforce_report_guardrails,
    render_json,
    render_report,
)
from agent.trace import AgentTrace, RunTrace, build_provenance_stamp
from agent.vcf_parser import parse_vcf

# ═══ Fixtures ═════════════════════════════════════════════════════════════════

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
VCF_PATH = str(FIXTURES_DIR / "tiny_truth.vcf")
VCF_GZ_PATH = str(FIXTURES_DIR / "tiny_truth.vcf.gz")
METRICS_PATH = str(FIXTURES_DIR / "HG002_chr20.metrics.json")


# ═══ Test: End-to-End Deterministic Agent ═════════════════════════════════════


class TestEndToEndDeterministic:
    """Full pipeline: VCF → deterministic interpreter → report."""

    def test_full_pipeline_produces_report(self):
        """The full pipeline (parse VCF → interpret → report) produces a valid report."""
        # Parse VCF
        variants = parse_vcf(VCF_PATH, max_variants=10)
        assert len(variants) >= 5

        # Interpret all variants
        interp = DeterministicInterpreter()
        results = interp.run_batch(variants)
        assert len(results) == len(variants)

        # Build report
        report = build_report(results, backend_used="deterministic", run_id="smoke_test")
        assert len(report.variants) == len(variants)
        assert report.provenance["run_id"] == "smoke_test"

        # Validate guardrails
        violations = enforce_report_guardrails(report)
        assert violations == [], f"Guardrail violations: {violations}"

    def test_text_report_has_banner_and_provenance(self):
        """Text report contains mandatory banner and provenance section."""
        variants = parse_vcf(VCF_PATH, max_variants=5)
        interp = DeterministicInterpreter()
        results = interp.run_batch(variants)
        report = build_report(results, backend_used="deterministic", run_id="smoke_banner")

        text = render_report(report)
        assert INTERPRETATION_BANNER in text
        assert "Provenance" in text
        assert "deterministic" in text

    def test_json_report_schema(self):
        """JSON report has all required top-level fields."""
        variants = parse_vcf(VCF_PATH, max_variants=5)
        interp = DeterministicInterpreter()
        results = interp.run_batch(variants)
        report = build_report(results, backend_used="deterministic", run_id="smoke_json")

        json_out = render_json(report)

        # Required fields
        assert "banner" in json_out
        assert "variants" in json_out
        assert "provenance" in json_out
        assert "disclaimer" in json_out
        assert "classification_counts" in json_out
        assert json_out["banner"] == INTERPRETATION_BANNER

        # Variants structure
        for v in json_out["variants"]:
            assert "classification" in v
            assert "evidence_codes" in v
            assert "variant" in v
            assert "is_vus" in v
            assert "requires_manual_review" in v

    def test_vus_variants_flagged(self):
        """VUS variants carry uncertainty statement in reports."""
        # Pick a variant we know will be VUS (unknown position)
        variant = Variant(chrom="chr20", pos=9999999, ref="A", alt="T", gene="")
        interp = DeterministicInterpreter()
        result = interp.run(variant)

        assert result.classification == "Uncertain Significance"

        report = build_report([result], backend_used="deterministic", run_id="smoke_vus")
        text = render_report(report)
        assert VUS_UNCERTAINTY_STATEMENT in text

        json_out = render_json(report)
        assert json_out["variants"][0]["requires_manual_review"] is True


# ═══ Test: ReAct Agent with Deterministic Backend ═════════════════════════════


class TestReActAgentSmoke:
    """ReAct agent with DeterministicBackend produces valid output."""

    def test_known_pathogenic_variant(self):
        """PRNP E200K is classified as Likely Pathogenic or Pathogenic."""
        agent = ReActAgent(backend=DeterministicBackend(), max_iterations=10)
        variant = Variant(chrom="chr20", pos=4699605, ref="G", alt="A", gene="PRNP")
        result = agent.run(variant)

        assert result.classification in ("Pathogenic", "Likely Pathogenic")
        assert not result.fallback_triggered
        assert len(result.trace) > 0
        assert len(result.evidence_codes) > 0

    def test_known_benign_variant(self):
        """PRNP M129V (AF=33.6%) is classified as Benign."""
        agent = ReActAgent(backend=DeterministicBackend(), max_iterations=10)
        variant = Variant(chrom="chr20", pos=4699517, ref="G", alt="A", gene="PRNP")
        result = agent.run(variant)

        assert result.classification == "Benign"
        assert "BA1" in result.evidence_codes

    def test_agent_trace_recorded(self):
        """Agent trace captures all tool calls."""
        agent = ReActAgent(backend=DeterministicBackend(), max_iterations=10)
        variant = Variant(chrom="chr20", pos=4699605, ref="G", alt="A", gene="PRNP")
        result = agent.run(variant)

        # Should have action steps (tool calls)
        actions = [s for s in result.trace if s.step_type == "action"]
        assert len(actions) >= 3  # At minimum: clinvar, gnomad, gene_info

        # Should have observations
        observations = [s for s in result.trace if s.step_type == "observation"]
        assert len(observations) >= 3

    def test_agent_trace_serializable(self):
        """Agent trace can be serialized to JSON without errors."""
        agent = ReActAgent(backend=DeterministicBackend(), max_iterations=10)
        variant = Variant(chrom="chr20", pos=4699605, ref="G", alt="A", gene="PRNP")
        result = agent.run(variant)

        trace = AgentTrace.from_result(result, run_id="smoke_trace")
        json_str = json.dumps(trace.to_dict())
        assert len(json_str) > 100

        # Round-trip
        parsed = json.loads(json_str)
        assert parsed["classification"] in ("Pathogenic", "Likely Pathogenic")


# ═══ Test: CLI Integration ════════════════════════════════════════════════════


class TestCLISmoke:
    """CLI produces correct output and exit codes."""

    def test_cli_deterministic_json_output(self):
        """CLI with --backend deterministic produces valid JSON."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = f.name

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "ai-report/agent/interpret.py",
                    "--vcf", VCF_PATH,
                    "--metrics", METRICS_PATH,
                    "--backend", "deterministic",
                    "--out", out_path,
                    "--run-id", "ci_smoke",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert result.returncode == 0, f"CLI failed: {result.stderr}"

            # Verify output file
            with open(out_path) as f:
                data = json.load(f)
            assert data["banner"] == INTERPRETATION_BANNER
            assert len(data["variants"]) > 0
            assert data["provenance"]["run_id"] == "ci_smoke"
        finally:
            Path(out_path).unlink(missing_ok=True)

    def test_cli_stdout_text_report(self):
        """CLI with no --out prints text report to stdout."""
        result = subprocess.run(
            [
                sys.executable,
                "ai-report/agent/interpret.py",
                "--vcf", VCF_PATH,
                "--backend", "deterministic",
                "--genes", "PRNP",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0
        assert INTERPRETATION_BANNER in result.stdout
        assert "PRNP" in result.stdout

    def test_cli_missing_vcf_exits_1(self):
        """CLI with nonexistent VCF exits with code 1."""
        result = subprocess.run(
            [
                sys.executable,
                "ai-report/agent/interpret.py",
                "--vcf", "/nonexistent/path.vcf",
                "--backend", "deterministic",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 1

    def test_cli_gzipped_vcf(self):
        """CLI handles gzipped VCF input."""
        result = subprocess.run(
            [
                sys.executable,
                "ai-report/agent/interpret.py",
                "--vcf", VCF_GZ_PATH,
                "--backend", "deterministic",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data["variants"]) > 0


# ═══ Test: Provenance ═════════════════════════════════════════════════════════


class TestProvenance:
    """Provenance stamps are complete and correct."""

    def test_provenance_stamp_has_required_fields(self):
        """Provenance stamp includes all required fields."""
        prov = build_provenance_stamp(
            backend_used="deterministic",
            run_id="prov_test",
            vcf_path="test.vcf",
        )
        assert prov["agent_version"] == "0.1.0"
        assert prov["backend"] == "deterministic"
        assert prov["knowledge_base"]["sha256"].startswith("sha256:")
        assert prov["knowledge_base"]["region"] == "chr20"
        assert prov["run_id"] == "prov_test"
        assert "timestamp" in prov
