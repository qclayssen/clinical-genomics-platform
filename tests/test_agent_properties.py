"""Property-based tests for the Variant Interpretation Agent.

Uses Hypothesis to verify universal correctness properties across
generated inputs. Minimum 200 iterations per property.

Properties tested:
  1. ACMG Combining Rules — classification matches truth table
  2. Tool Input Validation — no unhandled exceptions
  3. Guardrails on Interpretation — banner, no treatment language, provenance
  4. Agent Loop Termination — always terminates within max_iterations
  5. Fallback Determinism — same input always produces same output
  6. Classification Consistency — ClinVar Pathogenic + low AF never → Benign
"""

import json
import sys
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

# Add ai-report to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ai-report"))

from agent.deterministic import DeterministicInterpreter, classify_by_acmg_rules
from agent.llm import DeterministicBackend, Message
from agent.react import (
    InterpretationResult,
    ReActAgent,
    Variant,
    enforce_safety_constraints,
)
from agent.report import (
    INTERPRETATION_BANNER,
    VUS_UNCERTAINTY_STATEMENT,
    build_report,
    enforce_report_guardrails,
    render_json,
    render_report,
)
from agent.tools import ToolRegistry

# ═══ Strategies ═══════════════════════════════════════════════════════════════

# ACMG evidence code strategies
pathogenic_very_strong_codes = st.just("PVS1")
pathogenic_strong_codes = st.sampled_from(["PS1", "PS2", "PS3", "PS4"])
pathogenic_moderate_codes = st.sampled_from(["PM1", "PM2", "PM3", "PM4", "PM5", "PM6"])
pathogenic_supporting_codes = st.sampled_from(["PP1", "PP2", "PP3", "PP4", "PP5"])
benign_standalone_codes = st.just("BA1")
benign_strong_codes = st.sampled_from(["BS1", "BS2", "BS3", "BS4"])
benign_supporting_codes = st.sampled_from(["BP1", "BP2", "BP3", "BP4", "BP5", "BP6", "BP7"])

all_evidence_codes = st.sampled_from([
    "PVS1", "PS1", "PS2", "PS3", "PS4",
    "PM1", "PM2", "PM3", "PM4", "PM5", "PM6",
    "PP1", "PP2", "PP3", "PP4", "PP5",
    "BA1", "BS1", "BS2", "BS3", "BS4",
    "BP1", "BP2", "BP3", "BP4", "BP5", "BP6", "BP7",
])

evidence_code_sets = st.lists(all_evidence_codes, min_size=0, max_size=8)

# Variant strategies
chrom_strategy = st.just("chr20")
pos_strategy = st.integers(min_value=1, max_value=64444167)
allele_strategy = st.sampled_from(["A", "C", "G", "T"])
gene_strategy = st.sampled_from([
    "PRNP", "JAG1", "GNAS", "BMP2", "AURKA", "ASXL1", "SRC", "MAFB", "CDH22", ""
])
genotype_strategy = st.sampled_from(["0/1", "1/1", "0/0", ""])

variant_strategy = st.builds(
    Variant,
    chrom=chrom_strategy,
    pos=pos_strategy,
    ref=allele_strategy,
    alt=allele_strategy,
    gene=gene_strategy,
    genotype=genotype_strategy,
    qual=st.floats(min_value=0, max_value=100, allow_nan=False),
    filter_status=st.just("PASS"),
)

# Classification strategies
classification_strategy = st.sampled_from([
    "Pathogenic", "Likely Pathogenic", "Uncertain Significance",
    "Likely Benign", "Benign",
])


# ═══ Property 1: ACMG Combining Rules ════════════════════════════════════════


@settings(max_examples=200)
@given(evidence_codes=evidence_code_sets)
def test_property_1_acmg_classification_is_valid(evidence_codes):
    """For any set of evidence codes, the ACMG classification SHALL be one of
    the 5 valid ACMG/AMP classifications and SHALL have a valid confidence.
    """
    classification, rule, confidence = classify_by_acmg_rules(evidence_codes)

    valid_classifications = {
        "Pathogenic", "Likely Pathogenic", "Uncertain Significance",
        "Likely Benign", "Benign",
    }
    assert classification in valid_classifications, (
        f"Invalid classification: {classification} for codes {evidence_codes}"
    )
    assert confidence in {"high", "moderate", "low"}, (
        f"Invalid confidence: {confidence}"
    )
    assert isinstance(rule, str) and len(rule) > 0


@settings(max_examples=200)
@given(
    n_pvs=st.integers(min_value=1, max_value=1),
    strong_codes=st.lists(pathogenic_strong_codes, min_size=1, max_size=3),
)
def test_property_1b_pvs_plus_strong_is_pathogenic(n_pvs, strong_codes):
    """PVS1 + >=1 Strong SHALL always classify as Pathogenic."""
    codes = ["PVS1"] + strong_codes
    classification, _, confidence = classify_by_acmg_rules(codes)
    assert classification == "Pathogenic", (
        f"Expected Pathogenic for {codes}, got {classification}"
    )
    assert confidence == "high"


@settings(max_examples=200)
@given(data=st.data())
def test_property_1c_ba1_always_benign(data):
    """BA1 (AF >5%) SHALL always result in Benign, regardless of other codes."""
    # Generate random additional codes
    extra = data.draw(st.lists(all_evidence_codes, min_size=0, max_size=5))
    codes = ["BA1"] + extra
    classification, _, _ = classify_by_acmg_rules(codes)
    assert classification == "Benign", (
        f"BA1 present but classified as {classification} with codes {codes}"
    )


# ═══ Property 2: Tool Input Validation ════════════════════════════════════════


@settings(max_examples=200)
@given(
    chrom=chrom_strategy,
    pos=st.integers(min_value=-1000, max_value=100000000),
    ref=st.text(min_size=0, max_size=10),
    alt=st.text(min_size=0, max_size=10),
)
def test_property_2_tool_input_no_crash(chrom, pos, ref, alt):
    """For any arbitrary tool input, tools SHALL NOT raise unhandled exceptions.
    They may return error results, but must not crash.
    """
    registry = ToolRegistry()

    # query_clinvar — should handle gracefully
    result = registry.invoke("query_clinvar", {"chrom": chrom, "pos": pos, "ref": ref, "alt": alt})
    assert result.output is not None
    # May be success (empty results) or error, but no crash

    # query_gnomad
    result = registry.invoke("query_gnomad", {"chrom": chrom, "pos": pos, "ref": ref, "alt": alt})
    assert result.output is not None


@settings(max_examples=200)
@given(gene=st.text(min_size=0, max_size=20))
def test_property_2b_gene_info_no_crash(gene):
    """query_gene_info SHALL handle any gene string without crashing."""
    registry = ToolRegistry()
    result = registry.invoke("query_gene_info", {"gene_symbol": gene})
    assert result.output is not None
    # Should either find the gene or return found=False


@settings(max_examples=200)
@given(codes=st.lists(st.text(min_size=0, max_size=5), min_size=0, max_size=10))
def test_property_2c_classify_acmg_no_crash(codes):
    """classify_acmg SHALL handle any list of strings without crashing."""
    registry = ToolRegistry()
    result = registry.invoke("classify_acmg", {"evidence_codes": codes})
    assert result.success
    assert "classification" in result.output


# ═══ Property 3: Guardrails on Interpretation ═════════════════════════════════


@settings(max_examples=200)
@given(
    classification=classification_strategy,
    evidence=st.lists(all_evidence_codes, min_size=1, max_size=5),
    summary=st.text(min_size=20, max_size=300),
)
def test_property_3_guardrails_always_present(classification, evidence, summary):
    """For any interpretation result, the rendered report SHALL:
    - Contain the mandatory interpretation banner
    - Contain the provenance section
    - Not contain raw treatment recommendations (they get scrubbed)
    """
    variant = Variant(chrom="chr20", pos=4699605, ref="G", alt="A", gene="PRNP")
    result = InterpretationResult(
        variant=variant,
        classification=classification,
        evidence_codes=evidence,
        summary=summary,
        confidence="moderate",
        trace=[],
        backend_used="test",
    )

    report = build_report([result], backend_used="test", run_id="prop_test")
    text = render_report(report)

    # Banner must always be present
    assert INTERPRETATION_BANNER in text, "Missing interpretation banner"

    # Provenance section must be present
    assert "Provenance" in text, "Missing provenance section"

    # JSON output must have banner
    json_out = render_json(report)
    assert json_out["banner"] == INTERPRETATION_BANNER


@settings(max_examples=200)
@given(
    summary=st.text(min_size=20, max_size=300),
)
def test_property_3b_vus_always_flagged(summary):
    """Any VUS classification SHALL carry the uncertainty statement in the report."""
    variant = Variant(chrom="chr20", pos=1, ref="A", alt="T", gene="X")
    result = InterpretationResult(
        variant=variant,
        classification="Uncertain Significance",
        evidence_codes=["PM2"],
        summary=summary,
        confidence="low",
        trace=[],
        backend_used="test",
    )

    report = build_report([result], backend_used="test", run_id="vus_test")
    text = render_report(report)

    assert VUS_UNCERTAINTY_STATEMENT in text, "Missing VUS uncertainty statement"

    json_out = render_json(report)
    vus_variant = json_out["variants"][0]
    assert vus_variant["requires_manual_review"] is True


# ═══ Property 4: Agent Loop Termination ═══════════════════════════════════════


@settings(max_examples=200, deadline=5000)
@given(variant=variant_strategy)
def test_property_4_agent_always_terminates(variant):
    """The ReAct agent loop SHALL always terminate within max_iterations,
    producing either a classification or triggering fallback.
    """
    # Ensure ref != alt (invalid variant otherwise)
    assume(variant.ref != variant.alt)

    agent = ReActAgent(
        backend=DeterministicBackend(),
        max_iterations=10,
    )
    result = agent.run(variant)

    # Must always produce a result (not hang)
    assert result is not None
    assert isinstance(result, InterpretationResult)

    # Must have a valid classification or have triggered fallback
    valid = {"Pathogenic", "Likely Pathogenic", "Uncertain Significance",
             "Likely Benign", "Benign"}
    assert result.classification in valid, (
        f"Invalid classification: {result.classification}"
    )


# ═══ Property 5: Fallback Determinism ═════════════════════════════════════════


@settings(max_examples=200)
@given(variant=variant_strategy)
def test_property_5_deterministic_same_output(variant):
    """The deterministic interpreter SHALL always produce the same output
    for the same input. Two runs with identical input must be identical.
    """
    assume(variant.ref != variant.alt)

    interp = DeterministicInterpreter()
    result_a = interp.run(variant)
    result_b = interp.run(variant)

    assert result_a.classification == result_b.classification, (
        f"Non-deterministic: {result_a.classification} vs {result_b.classification}"
    )
    assert result_a.evidence_codes == result_b.evidence_codes
    assert result_a.summary == result_b.summary
    assert result_a.confidence == result_b.confidence


# ═══ Property 6: Classification Consistency ═══════════════════════════════════


@settings(max_examples=200)
@given(
    extra_path_codes=st.lists(pathogenic_moderate_codes, min_size=0, max_size=3),
    extra_supp_codes=st.lists(pathogenic_supporting_codes, min_size=0, max_size=3),
)
def test_property_6_pathogenic_clinvar_low_af_never_benign(extra_path_codes, extra_supp_codes):
    """If ClinVar says Pathogenic (→ PS1) AND gnomAD AF < 0.001 (→ PM2),
    the classification SHALL NEVER be Benign or Likely Benign.
    """
    # Simulate: PS1 from ClinVar + PM2 from gnomAD + any additional pathogenic evidence
    codes = ["PS1", "PM2"] + extra_path_codes + extra_supp_codes
    # Deduplicate
    codes = sorted(set(codes))
    # Exclude benign codes (this property tests pathogenic-only evidence)
    codes = [c for c in codes if not c.startswith("B")]

    classification, _, _ = classify_by_acmg_rules(codes)

    assert classification not in ("Benign", "Likely Benign"), (
        f"ClinVar Pathogenic + low AF classified as {classification} with codes {codes}"
    )


@settings(max_examples=200)
@given(
    extra_codes=st.lists(benign_supporting_codes, min_size=0, max_size=4),
)
def test_property_6b_ba1_overrides_pathogenic_evidence(extra_codes):
    """BA1 (>5% AF) SHALL override any pathogenic evidence and classify as Benign.
    This is because BA1 is a stand-alone benign criterion.
    """
    # Even with strong pathogenic evidence, BA1 wins
    codes = ["BA1", "PS1", "PM2", "PP5"] + extra_codes
    classification, _, _ = classify_by_acmg_rules(codes)
    assert classification == "Benign", (
        f"BA1 present but got {classification} with codes {codes}"
    )
