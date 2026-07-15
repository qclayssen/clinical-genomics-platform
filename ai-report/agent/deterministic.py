"""Deterministic variant interpretation pipeline (no-LLM fallback).

When the ReAct agent fails (LLM unavailable, loops, or exceeds budget),
this module executes a fixed interpretation pipeline:
  1. Parse variants
  2. Query ClinVar for existing classifications
  3. Query gnomAD for population allele frequencies
  4. Apply ACMG combining rules (pure functions)
  5. Generate a template-based report

This guarantees a classification is always produced — the platform never
hard-fails. The deterministic path produces the same output for the same
input every time, making it ideal for CI and regression testing.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from .data.knowledge_base import KnowledgeBase
from .react import InterpretationResult, TraceStep, Variant
from .tools import ToolRegistry

logger = logging.getLogger(__name__)


# ═══ ACMG Combining Rules (Pure Functions) ════════════════════════════════════


def classify_by_acmg_rules(evidence_codes: list[str]) -> tuple[str, str, str]:
    """Apply ACMG/AMP 2015 combining rules to evidence codes.

    Pure function — no side effects, fully deterministic.

    Parameters
    ----------
    evidence_codes : list[str]
        ACMG evidence codes (e.g., ['PS1', 'PM2', 'PP5']).

    Returns
    -------
    tuple[str, str, str]
        (classification, matched_rule, confidence)
    """
    pvs = [c for c in evidence_codes if c.startswith("PVS")]
    ps = [c for c in evidence_codes if c.startswith("PS")]
    pm = [c for c in evidence_codes if c.startswith("PM")]
    pp = [c for c in evidence_codes if c.startswith("PP")]
    ba = [c for c in evidence_codes if c.startswith("BA")]
    bs = [c for c in evidence_codes if c.startswith("BS")]
    bp = [c for c in evidence_codes if c.startswith("BP")]

    n_pvs, n_ps, n_pm, n_pp = len(pvs), len(ps), len(pm), len(pp)
    n_ba, n_bs, n_bp = len(ba), len(bs), len(bp)

    # Benign rules (BA1 is stand-alone)
    if n_ba >= 1:
        return ("Benign", "BA1: allele frequency >5%", "high")
    if n_bs >= 2:
        return ("Benign", f">=2 Strong benign: {', '.join(bs)}", "high")
    if n_bs >= 1 and n_bp >= 1:
        return ("Likely Benign", f"1 Strong + Supporting benign: {', '.join(bs + bp)}", "moderate")
    if n_bp >= 2:
        return ("Likely Benign", f">=2 Supporting benign: {', '.join(bp)}", "moderate")

    # Pathogenic rules
    if n_pvs >= 1 and n_ps >= 1:
        return ("Pathogenic", f"Very Strong + Strong: {', '.join(pvs + ps)}", "high")
    if n_pvs >= 1 and n_pm >= 2:
        return ("Pathogenic", f"Very Strong + >=2 Moderate: {', '.join(pvs + pm)}", "high")
    if n_pvs >= 1 and n_pm >= 1 and n_pp >= 1:
        return ("Pathogenic", f"Very Strong + Moderate + Supporting: {', '.join(pvs + pm + pp)}", "high")
    if n_pvs >= 1 and n_pp >= 2:
        return ("Pathogenic", f"Very Strong + >=2 Supporting: {', '.join(pvs + pp)}", "high")
    if n_ps >= 2:
        return ("Pathogenic", f">=2 Strong: {', '.join(ps)}", "high")
    if n_ps >= 1 and n_pm >= 3:
        return ("Pathogenic", f"1 Strong + >=3 Moderate: {', '.join(ps + pm)}", "high")
    if n_ps >= 1 and n_pm >= 2 and n_pp >= 2:
        return ("Pathogenic", f"1 Strong + 2 Moderate + >=2 Supporting: {', '.join(ps + pm + pp)}", "high")
    if n_ps >= 1 and n_pm >= 1 and n_pp >= 4:
        return ("Pathogenic", f"1 Strong + 1 Moderate + >=4 Supporting: {', '.join(ps + pm + pp)}", "high")

    # Likely Pathogenic rules
    if n_pvs >= 1 and n_pm >= 1:
        return ("Likely Pathogenic", f"Very Strong + Moderate: {', '.join(pvs + pm)}", "moderate")
    if n_ps >= 1 and n_pm >= 1:
        return ("Likely Pathogenic", f"1 Strong + 1-2 Moderate: {', '.join(ps + pm)}", "moderate")
    if n_ps >= 1 and n_pp >= 2:
        return ("Likely Pathogenic", f"1 Strong + >=2 Supporting: {', '.join(ps + pp)}", "moderate")
    if n_pm >= 3:
        return ("Likely Pathogenic", f">=3 Moderate: {', '.join(pm)}", "moderate")
    if n_pm >= 2 and n_pp >= 2:
        return ("Likely Pathogenic", f"2 Moderate + >=2 Supporting: {', '.join(pm + pp)}", "moderate")
    if n_pm >= 1 and n_pp >= 4:
        return ("Likely Pathogenic", f"1 Moderate + >=4 Supporting: {', '.join(pm + pp)}", "moderate")

    return ("Uncertain Significance", "No combining rule met", "low")


# ═══ Deterministic Interpreter ════════════════════════════════════════════════


class DeterministicInterpreter:
    """No-LLM variant interpretation pipeline.

    Executes a fixed sequence of knowledge base queries and applies
    ACMG combining rules deterministically. Same input always produces
    same output.

    Parameters
    ----------
    kb : KnowledgeBase, optional
        Knowledge base instance. Creates a new one if not provided.
    """

    def __init__(self, kb: Optional[KnowledgeBase] = None) -> None:
        self._kb = kb or KnowledgeBase()

    def run(self, variant: Variant) -> InterpretationResult:
        """Interpret a single variant using the deterministic pipeline.

        Pipeline:
        1. ClinVar lookup → extract significance + evidence
        2. gnomAD lookup → extract frequency-based codes
        3. Gene lookup → contextualize
        4. ACMG combining rules → classification
        5. Template summary generation

        Parameters
        ----------
        variant : Variant
            The variant to interpret.

        Returns
        -------
        InterpretationResult
            Classification with full trace.
        """
        start_time = time.perf_counter()
        trace: list[TraceStep] = []
        evidence_codes: list[str] = []

        # ── Step 1: ClinVar lookup ─────────────────────────────────────────
        trace.append(TraceStep(
            step_type="action",
            content="Querying ClinVar (deterministic path)",
            timestamp=time.time(),
            tool_name="query_clinvar",
            tool_input={"chrom": variant.chrom, "pos": variant.pos, "ref": variant.ref, "alt": variant.alt},
        ))

        clinvar_records = self._kb.query_clinvar(variant.chrom, variant.pos, variant.ref, variant.alt)
        clinvar_sig = None
        clinvar_stars = 0
        clinvar_conditions = ""

        if clinvar_records:
            rec = clinvar_records[0]
            clinvar_sig = rec.clinical_significance
            clinvar_stars = rec.review_stars
            clinvar_conditions = rec.conditions or ""

            # Derive evidence codes from ClinVar
            if clinvar_sig == "Pathogenic" and clinvar_stars >= 2:
                evidence_codes.append("PS1")  # Same AA change as established pathogenic
                evidence_codes.append("PP5")  # Reputable source reports pathogenic
            elif clinvar_sig == "Pathogenic" and clinvar_stars == 1:
                evidence_codes.append("PP5")  # Single submitter — supporting only
            elif clinvar_sig == "Likely Pathogenic" and clinvar_stars >= 2:
                evidence_codes.append("PP5")
            elif clinvar_sig == "Benign" and clinvar_stars >= 2:
                evidence_codes.append("BP6")
            elif clinvar_sig == "Likely Benign" and clinvar_stars >= 2:
                evidence_codes.append("BP6")

            trace.append(TraceStep(
                step_type="observation",
                content=f"ClinVar: {clinvar_sig} ({clinvar_stars} stars)",
                timestamp=time.time(),
                tool_name="query_clinvar",
                tool_output={"clinical_significance": clinvar_sig, "review_stars": clinvar_stars},
            ))
        else:
            trace.append(TraceStep(
                step_type="observation",
                content="ClinVar: no record found",
                timestamp=time.time(),
                tool_name="query_clinvar",
                tool_output={"found": False},
            ))

        # ── Step 2: gnomAD lookup ──────────────────────────────────────────
        trace.append(TraceStep(
            step_type="action",
            content="Querying gnomAD (deterministic path)",
            timestamp=time.time(),
            tool_name="query_gnomad",
            tool_input={"chrom": variant.chrom, "pos": variant.pos, "ref": variant.ref, "alt": variant.alt},
        ))

        gnomad_record = self._kb.query_gnomad(variant.chrom, variant.pos, variant.ref, variant.alt)
        af_global = 0.0

        if gnomad_record:
            af_global = gnomad_record.af_global

            # Derive frequency-based evidence codes
            if af_global > 0.05:
                evidence_codes.append("BA1")
            elif af_global > 0.01:
                evidence_codes.append("BS1")
            elif af_global < 0.0001:
                evidence_codes.append("PM2")

            if gnomad_record.homozygote_count > 0 and af_global > 0.01:
                evidence_codes.append("BS2")

            trace.append(TraceStep(
                step_type="observation",
                content=f"gnomAD: AF={af_global:.6f}",
                timestamp=time.time(),
                tool_name="query_gnomad",
                tool_output={"af_global": af_global, "homozygote_count": gnomad_record.homozygote_count},
            ))
        else:
            # Absent from gnomAD → PM2
            evidence_codes.append("PM2")
            trace.append(TraceStep(
                step_type="observation",
                content="gnomAD: variant absent (supports PM2)",
                timestamp=time.time(),
                tool_name="query_gnomad",
                tool_output={"found": False, "af_global": 0.0},
            ))

        # ── Step 3: Gene info (context only) ───────────────────────────────
        gene_symbol = variant.gene or self._kb.position_to_gene(variant.chrom, variant.pos)
        gene_description = ""

        if gene_symbol:
            gene_records = self._kb.get_gene_info(gene_symbol)
            if gene_records:
                gene_description = gene_records[0].description
            trace.append(TraceStep(
                step_type="observation",
                content=f"Gene: {gene_symbol} — {gene_description}",
                timestamp=time.time(),
                tool_name="query_gene_info",
                tool_output={"gene_symbol": gene_symbol, "description": gene_description},
            ))

        # ── Step 4: ACMG combining rules ──────────────────────────────────
        # Deduplicate evidence codes
        evidence_codes = sorted(set(evidence_codes))

        classification, matched_rule, confidence = classify_by_acmg_rules(evidence_codes)

        trace.append(TraceStep(
            step_type="action",
            content=f"ACMG classification: {classification} (rule: {matched_rule})",
            timestamp=time.time(),
            tool_name="classify_acmg",
            tool_input={"evidence_codes": evidence_codes},
            tool_output={"classification": classification, "matched_rule": matched_rule},
        ))

        # ── Step 5: Generate summary ──────────────────────────────────────
        summary = self._generate_summary(
            variant=variant,
            classification=classification,
            evidence_codes=evidence_codes,
            matched_rule=matched_rule,
            clinvar_sig=clinvar_sig,
            clinvar_stars=clinvar_stars,
            clinvar_conditions=clinvar_conditions,
            af_global=af_global,
            gene_symbol=gene_symbol or "unknown",
            gene_description=gene_description,
        )

        trace.append(TraceStep(
            step_type="answer",
            content=summary,
            timestamp=time.time(),
        ))

        wall_time = (time.perf_counter() - start_time) * 1000

        return InterpretationResult(
            variant=variant,
            classification=classification,
            evidence_codes=evidence_codes,
            summary=summary,
            confidence=confidence,
            trace=trace,
            backend_used="deterministic-fallback",
            fallback_triggered=True,
            total_tokens=0,
            wall_time_ms=wall_time,
        )

    def run_batch(self, variants: list[Variant]) -> list[InterpretationResult]:
        """Interpret a batch of variants deterministically."""
        return [self.run(v) for v in variants]

    def _generate_summary(
        self,
        variant: Variant,
        classification: str,
        evidence_codes: list[str],
        matched_rule: str,
        clinvar_sig: Optional[str],
        clinvar_stars: int,
        clinvar_conditions: str,
        af_global: float,
        gene_symbol: str,
        gene_description: str,
    ) -> str:
        """Generate a template-based interpretation summary."""
        parts: list[str] = []

        # Variant identifier
        parts.append(
            f"Variant {variant.chrom}:{variant.pos} {variant.ref}>{variant.alt} "
            f"in gene {gene_symbol} is classified as {classification}."
        )

        # ClinVar evidence
        if clinvar_sig:
            star_note = ""
            if clinvar_stars < 2:
                star_note = " (note: single-submitter evidence — lower confidence)"
            parts.append(
                f"ClinVar reports this variant as {clinvar_sig}{star_note}."
            )
            if clinvar_conditions and clinvar_conditions != "not specified":
                parts.append(f"Associated condition(s): {clinvar_conditions}.")
        else:
            parts.append("This variant has no existing ClinVar record.")

        # Frequency evidence
        if af_global > 0.05:
            parts.append(
                f"Population frequency (gnomAD AF={af_global:.4f}) exceeds 5%, "
                f"meeting the BA1 stand-alone benign criterion."
            )
        elif af_global > 0.01:
            parts.append(
                f"Population frequency (gnomAD AF={af_global:.4f}) exceeds 1%, "
                f"supporting benign classification (BS1)."
            )
        elif af_global > 0:
            parts.append(
                f"Population frequency is very low (gnomAD AF={af_global:.6f}), "
                f"supporting pathogenic classification (PM2)."
            )
        else:
            parts.append(
                "This variant is absent from gnomAD, supporting PM2 "
                "(absent from population controls)."
            )

        # ACMG rule
        parts.append(f"ACMG combining rule applied: {matched_rule}.")
        parts.append(f"Evidence codes: {', '.join(evidence_codes)}.")

        # VUS uncertainty flag
        if classification == "Uncertain Significance":
            parts.append(
                "UNCERTAINTY NOTE: This variant does not meet criteria for "
                "pathogenic or benign classification. Additional functional studies, "
                "segregation data, or de novo status information may help resolve "
                "this classification. Manual review by a clinical geneticist is required."
            )

        return " ".join(parts)
