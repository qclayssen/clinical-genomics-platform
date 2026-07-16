"""Interpretation report generator with guardrails.

Takes the agent's structured output and produces human-readable,
guardrailed interpretation reports in both text and JSON formats.

Guardrails (non-negotiable, enforced in code):
  1. Mandatory banner: AI-DRAFTED VARIANT INTERPRETATION — REQUIRES CLINICAL GENETICIST REVIEW
  2. Provenance line with model, backend, tool versions, KB version
  3. Strip treatment/diagnosis language
  4. Flag all VUS with explicit uncertainty statement
  5. No clinical recommendations
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .react import InterpretationResult, Variant, enforce_safety_constraints

# ═══ Constants ════════════════════════════════════════════════════════════════

INTERPRETATION_BANNER = (
    "AI-DRAFTED VARIANT INTERPRETATION — REQUIRES CLINICAL GENETICIST REVIEW"
)

VUS_UNCERTAINTY_STATEMENT = (
    "This variant is classified as a Variant of Uncertain Significance (VUS). "
    "Additional evidence (functional studies, segregation data, or population data) "
    "is needed to resolve this classification. This result MUST be reviewed by a "
    "qualified clinical geneticist before any clinical action."
)


# ═══ Report Data Structures ═══════════════════════════════════════════════════


@dataclass
class VariantInterpretation:
    """Interpretation of a single variant."""

    variant: Variant
    classification: str
    evidence_codes: list[str]
    confidence: str
    summary: str
    reasoning_trace: list[dict] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "variant": {
                "chrom": self.variant.chrom,
                "pos": self.variant.pos,
                "ref": self.variant.ref,
                "alt": self.variant.alt,
                "gene": self.variant.gene,
                "genotype": self.variant.genotype,
            },
            "classification": self.classification,
            "evidence_codes": self.evidence_codes,
            "confidence": self.confidence,
            "summary": self.summary,
            "citations": self.citations,
            "is_vus": self.classification == "Uncertain Significance",
        }


@dataclass
class InterpretationReport:
    """Full interpretation report for a set of variants."""

    variants: list[VariantInterpretation] = field(default_factory=list)
    summary: str = ""
    provenance: dict = field(default_factory=dict)
    agent_trace: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "banner": INTERPRETATION_BANNER,
            "report_version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "variants": [v.to_dict() for v in self.variants],
            "summary": self.summary,
            "provenance": self.provenance,
            "metadata": self.metadata,
            "classification_counts": self._classification_counts(),
        }

    def _classification_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for v in self.variants:
            counts[v.classification] = counts.get(v.classification, 0) + 1
        return counts


# ═══ Report Builder ═══════════════════════════════════════════════════════════


def build_report(
    results: list[InterpretationResult],
    backend_used: str = "deterministic",
    run_id: str = "",
    vcf_path: str = "",
    metrics_path: str = "",
) -> InterpretationReport:
    """Build an InterpretationReport from a list of agent results.

    Applies guardrails to each variant interpretation and assembles
    the complete report structure.

    Parameters
    ----------
    results : list[InterpretationResult]
        Raw results from the ReAct agent or deterministic interpreter.
    backend_used : str
        LLM backend identifier for provenance.
    run_id : str
        Pipeline run identifier.
    vcf_path : str
        Path to the source VCF file.
    metrics_path : str
        Path to the metrics.json file.

    Returns
    -------
    InterpretationReport
        Guardrailed report ready for rendering.
    """
    variant_interpretations: list[VariantInterpretation] = []
    all_traces: list[dict] = []

    for result in results:
        # Apply safety constraints to summary
        summary, violations = enforce_safety_constraints(result.summary)

        # Build citations from evidence
        citations = _build_citations(result.evidence_codes)

        vi = VariantInterpretation(
            variant=result.variant,
            classification=result.classification,
            evidence_codes=result.evidence_codes,
            confidence=result.confidence,
            summary=summary,
            reasoning_trace=[s.to_dict() for s in result.trace],
            citations=citations,
        )
        variant_interpretations.append(vi)

        # Collect traces
        all_traces.append({
            "variant": str(result.variant),
            "steps": len(result.trace),
            "backend": result.backend_used,
            "fallback": result.fallback_triggered,
            "wall_time_ms": result.wall_time_ms,
        })

    # Build provenance
    provenance = {
        "agent_version": "0.1.0",
        "backend": backend_used,
        "knowledge_base_version": "1.0.0",
        "knowledge_base_region": "chr20",
        "acmg_guidelines": "ACMG/AMP 2015 (Richards et al.)",
        "run_id": run_id or f"interp_{int(time.time())}",
        "vcf_source": vcf_path,
        "metrics_source": metrics_path,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Build summary
    n_total = len(variant_interpretations)
    counts = {}
    for vi in variant_interpretations:
        counts[vi.classification] = counts.get(vi.classification, 0) + 1

    summary_parts = [f"{n_total} variant(s) interpreted."]
    for cls in ["Pathogenic", "Likely Pathogenic", "Uncertain Significance", "Likely Benign", "Benign"]:
        if cls in counts:
            summary_parts.append(f"{counts[cls]} {cls}.")
    summary = " ".join(summary_parts)

    return InterpretationReport(
        variants=variant_interpretations,
        summary=summary,
        provenance=provenance,
        agent_trace=all_traces,
        metadata={
            "n_variants": n_total,
            "n_vus": counts.get("Uncertain Significance", 0),
            "any_fallback": any(r.fallback_triggered for r in results),
        },
    )


def _build_citations(evidence_codes: list[str]) -> list[str]:
    """Build citation references from evidence codes."""
    citations = []
    for code in evidence_codes:
        if code.startswith("BA") or code.startswith("BS") or code.startswith("PM2"):
            citations.append("gnomAD v4.1 (Karczewski et al., Nature 2020)")
        elif code.startswith("PS1") or code.startswith("PP5") or code.startswith("BP6"):
            citations.append("ClinVar (Landrum et al., NAR 2020)")
        elif code.startswith("PVS1"):
            citations.append("Loss-of-function variant interpretation (Abou Tayoun et al., 2018)")
    return sorted(set(citations))


# ═══ Rendering Functions ══════════════════════════════════════════════════════


def render_report(report: InterpretationReport) -> str:
    """Render the report as human-readable plain text.

    Enforces all guardrails: banner, provenance, VUS flags, no treatment language.

    Parameters
    ----------
    report : InterpretationReport
        The structured report to render.

    Returns
    -------
    str
        Formatted text report.
    """
    lines: list[str] = []

    # ── Mandatory banner ───────────────────────────────────────────────────
    lines.append("=" * 76)
    lines.append(INTERPRETATION_BANNER)
    lines.append("=" * 76)
    lines.append("")

    # ── Summary ────────────────────────────────────────────────────────────
    lines.append(f"Summary: {report.summary}")
    lines.append("")

    # ── Variant interpretations ────────────────────────────────────────────
    for i, vi in enumerate(report.variants, 1):
        lines.append(f"─── Variant {i}/{len(report.variants)} ───")
        lines.append(f"  Location:       {vi.variant.chrom}:{vi.variant.pos}")
        lines.append(f"  Change:         {vi.variant.ref} > {vi.variant.alt}")
        if vi.variant.gene:
            lines.append(f"  Gene:           {vi.variant.gene}")
        if vi.variant.genotype:
            lines.append(f"  Genotype:       {vi.variant.genotype}")
        lines.append(f"  Classification: {vi.classification}")
        lines.append(f"  Confidence:     {vi.confidence}")
        lines.append(f"  Evidence:       {', '.join(vi.evidence_codes)}")
        lines.append(f"  Reasoning:      {vi.summary}")

        # VUS uncertainty flag (mandatory)
        if vi.classification == "Uncertain Significance":
            lines.append(f"  ⚠ {VUS_UNCERTAINTY_STATEMENT}")

        if vi.citations:
            lines.append(f"  Citations:      {'; '.join(vi.citations)}")
        lines.append("")

    # ── Provenance ─────────────────────────────────────────────────────────
    lines.append("─── Provenance ───")
    prov = report.provenance
    lines.append(f"  Agent version:  {prov.get('agent_version', '?')}")
    lines.append(f"  Backend:        {prov.get('backend', '?')}")
    lines.append(f"  Knowledge base: v{prov.get('knowledge_base_version', '?')} ({prov.get('knowledge_base_region', '?')})")
    lines.append(f"  Guidelines:     {prov.get('acmg_guidelines', '?')}")
    lines.append(f"  Run ID:         {prov.get('run_id', '?')}")
    lines.append(f"  Generated:      {prov.get('generated_at', '?')}")
    if prov.get("vcf_source"):
        lines.append(f"  VCF source:     {prov['vcf_source']}")
    lines.append("")

    # ── Footer ─────────────────────────────────────────────────────────────
    lines.append("=" * 76)
    lines.append("This interpretation is AI-generated and MUST be reviewed by a qualified")
    lines.append("clinical geneticist before any clinical decision-making.")
    lines.append("=" * 76)

    return "\n".join(lines)


def render_json(report: InterpretationReport) -> dict:
    """Render the report as a structured JSON-serializable dict.

    Enforces guardrails: banner field always present, VUS flags included.

    Parameters
    ----------
    report : InterpretationReport
        The structured report to render.

    Returns
    -------
    dict
        JSON-serializable report with all guardrail fields.
    """
    output = report.to_dict()

    # Ensure banner is always present (guardrail)
    output["banner"] = INTERPRETATION_BANNER

    # Add VUS flags
    for v in output["variants"]:
        if v["classification"] == "Uncertain Significance":
            v["vus_uncertainty_statement"] = VUS_UNCERTAINTY_STATEMENT
            v["requires_manual_review"] = True
        else:
            v["requires_manual_review"] = False

    # Footer disclaimer
    output["disclaimer"] = (
        "This interpretation is AI-generated and MUST be reviewed by a qualified "
        "clinical geneticist before any clinical decision-making."
    )

    return output


def enforce_report_guardrails(report: InterpretationReport) -> list[str]:
    """Validate that all guardrails are satisfied on the report.

    Returns a list of violations (empty = compliant).
    """
    violations: list[str] = []

    # Check banner would be present in rendered output
    text = render_report(report)
    if INTERPRETATION_BANNER not in text:
        violations.append("Missing mandatory interpretation banner")

    # Check provenance
    if not report.provenance:
        violations.append("Missing provenance information")
    elif not report.provenance.get("agent_version"):
        violations.append("Missing agent_version in provenance")

    # Check VUS uncertainty statements
    for vi in report.variants:
        if vi.classification == "Uncertain Significance":
            if VUS_UNCERTAINTY_STATEMENT not in text:
                violations.append(f"Missing VUS uncertainty statement for {vi.variant}")

    # Check for treatment language in summaries
    for vi in report.variants:
        _, summary_violations = enforce_safety_constraints(vi.summary)
        if summary_violations:
            violations.append(f"Treatment language in summary for {vi.variant}: {summary_violations}")

    # Check evidence codes present
    for vi in report.variants:
        if not vi.evidence_codes:
            violations.append(f"No evidence codes for {vi.variant}")

    return violations
