"""Agent tool definitions and implementations.

Defines the tool-use protocol for the ReAct variant interpretation agent.
Each tool has a JSON Schema definition for input parameters, a callable
implementation, and structured JSON output with provenance logging.

Tools:
  1. query_clinvar — Look up ClinVar clinical significance for a variant
  2. query_gnomad — Look up gnomAD population allele frequency for a variant
  3. query_gene_info — Get gene function and disease associations
  4. classify_acmg — Apply ACMG/AMP combining rules to evidence codes
  5. final_answer — Terminate the agent loop with a structured classification
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .data.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


# ═══ Tool Protocol ════════════════════════════════════════════════════════════


@dataclass
class ToolDefinition:
    """Definition of an agent tool with JSON Schema parameters.

    Attributes
    ----------
    name : str
        Tool identifier used in function-calling protocol.
    description : str
        Human-readable description of what the tool does (shown to the LLM).
    parameters : dict
        JSON Schema object describing the tool's input parameters.
    function : Callable
        The implementation function to call when the tool is invoked.
    """

    name: str
    description: str
    parameters: dict
    function: Callable[..., dict]

    def to_schema(self) -> dict:
        """Return the tool definition in OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic_schema(self) -> dict:
        """Return the tool definition in Anthropic tool-use format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


@dataclass
class ToolResult:
    """Result of a tool invocation with metadata.

    Attributes
    ----------
    tool_name : str
        Name of the tool that was invoked.
    input_args : dict
        Arguments passed to the tool.
    output : dict
        Structured JSON output from the tool.
    success : bool
        Whether the tool executed successfully.
    error : str or None
        Error message if the tool failed.
    duration_ms : float
        Execution time in milliseconds.
    """

    tool_name: str
    input_args: dict
    output: dict
    success: bool = True
    error: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "input_args": self.input_args,
            "output": self.output,
            "success": self.success,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


# ═══ Tool Implementations ═════════════════════════════════════════════════════


def _query_clinvar(
    chrom: str, pos: int, ref: str, alt: str, *, _kb: Optional[KnowledgeBase] = None
) -> dict:
    """Look up ClinVar clinical significance for a variant.

    Queries the local SQLite knowledge base first. Returns structured
    ClinVar records including significance, review status, and conditions.
    """
    kb = _kb or KnowledgeBase()
    try:
        records = kb.query_clinvar(chrom, pos, ref, alt)
        if not records:
            return {
                "found": False,
                "variant": f"{chrom}:{pos} {ref}>{alt}",
                "message": "No ClinVar record found for this variant",
                "records": [],
            }

        return {
            "found": True,
            "variant": f"{chrom}:{pos} {ref}>{alt}",
            "n_records": len(records),
            "records": [r.to_dict() for r in records],
        }
    finally:
        if _kb is None:
            kb.close()


def _query_gnomad(
    chrom: str, pos: int, ref: str, alt: str, *, _kb: Optional[KnowledgeBase] = None
) -> dict:
    """Look up gnomAD population allele frequency for a variant.

    Returns global AF, population-maximum AF, homozygote count, and
    ACMG frequency-based evidence assessment.
    """
    kb = _kb or KnowledgeBase()
    try:
        record = kb.query_gnomad(chrom, pos, ref, alt)
        if record is None:
            return {
                "found": False,
                "variant": f"{chrom}:{pos} {ref}>{alt}",
                "af_global": 0.0,
                "af_popmax": 0.0,
                "homozygote_count": 0,
                "frequency_interpretation": "Absent from gnomAD — supports PM2 (absent from controls)",
                "acmg_frequency_codes": ["PM2"],
            }

        # Determine ACMG frequency-based evidence codes
        acmg_codes: list[str] = []
        interpretation_parts: list[str] = []

        af = record.af_global
        if af > 0.05:
            acmg_codes.append("BA1")
            interpretation_parts.append(
                f"AF={af:.4f} exceeds 5% threshold — BA1 (stand-alone benign)"
            )
        elif af > 0.01:
            acmg_codes.append("BS1")
            interpretation_parts.append(
                f"AF={af:.4f} exceeds 1% threshold — BS1 (strong benign)"
            )
        elif af < 0.0001:
            acmg_codes.append("PM2")
            interpretation_parts.append(
                f"AF={af:.6f} below 0.01% — PM2 (absent/rare in controls)"
            )

        if record.homozygote_count > 0 and af > 0.01:
            acmg_codes.append("BS2")
            interpretation_parts.append(
                f"{record.homozygote_count} homozygotes in gnomAD — BS2 (observed in healthy adults)"
            )

        freq_interp = "; ".join(interpretation_parts) if interpretation_parts else (
            f"AF={af:.6f} — moderate frequency, no strong ACMG frequency evidence"
        )

        return {
            "found": True,
            "variant": f"{chrom}:{pos} {ref}>{alt}",
            "af_global": record.af_global,
            "af_popmax": record.af_popmax,
            "homozygote_count": record.homozygote_count,
            "filter_status": record.filter_status,
            "frequency_interpretation": freq_interp,
            "acmg_frequency_codes": acmg_codes,
        }
    finally:
        if _kb is None:
            kb.close()


def _query_gene_info(
    gene_symbol: str, *, _kb: Optional[KnowledgeBase] = None
) -> dict:
    """Get gene function, disease associations, and genomic coordinates.

    Combines data from the gene BED index and the ClinVar annotations JSONL
    to provide context about the gene's role in disease.
    """
    kb = _kb or KnowledgeBase()
    try:
        gene_records = kb.get_gene_info(gene_symbol)
        clinvar_records = kb.query_clinvar_by_gene(gene_symbol)

        if not gene_records:
            return {
                "found": False,
                "gene_symbol": gene_symbol,
                "message": f"No annotation found for gene {gene_symbol} in chr20 knowledge base",
            }

        gene = gene_records[0]

        # Summarize ClinVar variant landscape for this gene
        significance_counts: dict[str, int] = {}
        conditions: set[str] = set()
        for cv in clinvar_records:
            sig = cv.clinical_significance
            significance_counts[sig] = significance_counts.get(sig, 0) + 1
            if cv.conditions and cv.conditions != "not specified":
                conditions.add(cv.conditions)

        return {
            "found": True,
            "gene_symbol": gene.gene_symbol,
            "chrom": gene.chrom,
            "start": gene.start,
            "end": gene.end,
            "strand": gene.strand,
            "description": gene.description,
            "clinvar_variant_count": len(clinvar_records),
            "clinvar_significance_summary": significance_counts,
            "associated_conditions": sorted(conditions),
            "gene_size_bp": gene.end - gene.start,
        }
    finally:
        if _kb is None:
            kb.close()


def _classify_acmg(
    evidence_codes: list[str], *, _kb: Optional[KnowledgeBase] = None
) -> dict:
    """Apply ACMG/AMP combining rules to determine pathogenicity classification.

    Takes a list of evidence codes (e.g., ['PS1', 'PM2', 'PP3']) and returns
    the resulting classification according to the 2015 ACMG/AMP guidelines.

    Delegates to the canonical implementation in deterministic.py to avoid
    rule duplication.

    Returns
    -------
    dict with:
        - classification: str (Pathogenic/Likely Pathogenic/Uncertain Significance/Likely Benign/Benign)
        - evidence_summary: dict of code categories and counts
        - matched_rule: str describing which combining rule was triggered
        - confidence: str (high/moderate/low)
    """
    from .deterministic import classify_by_acmg_rules

    # Categorize evidence codes by strength for the summary
    pvs = [c for c in evidence_codes if c.startswith("PVS")]
    ps = [c for c in evidence_codes if c.startswith("PS")]
    pm = [c for c in evidence_codes if c.startswith("PM")]
    pp = [c for c in evidence_codes if c.startswith("PP")]
    ba = [c for c in evidence_codes if c.startswith("BA")]
    bs = [c for c in evidence_codes if c.startswith("BS")]
    bp = [c for c in evidence_codes if c.startswith("BP")]

    classification, matched_rule, confidence = classify_by_acmg_rules(evidence_codes)

    evidence_summary = {
        "very_strong_pathogenic": pvs,
        "strong_pathogenic": ps,
        "moderate_pathogenic": pm,
        "supporting_pathogenic": pp,
        "stand_alone_benign": ba,
        "strong_benign": bs,
        "supporting_benign": bp,
    }

    return {
        "classification": classification,
        "evidence_codes": evidence_codes,
        "evidence_summary": {k: v for k, v in evidence_summary.items() if v},
        "matched_rule": matched_rule,
        "confidence": confidence,
        "n_pathogenic_evidence": len(pvs) + len(ps) + len(pm) + len(pp),
        "n_benign_evidence": len(ba) + len(bs) + len(bp),
    }


def _final_answer(
    classification: str,
    evidence: list[str],
    summary: str,
    variant: Optional[str] = None,
    confidence: Optional[str] = None,
) -> dict:
    """Terminate the agent loop with a structured classification result.

    This is the only tool that signals the agent loop to stop. The agent
    MUST call this tool to produce its final output.
    """
    valid_classifications = {
        "Pathogenic", "Likely Pathogenic", "Uncertain Significance",
        "Likely Benign", "Benign",
    }

    if classification not in valid_classifications:
        return {
            "success": False,
            "error": f"Invalid classification '{classification}'. Must be one of: {sorted(valid_classifications)}",
        }

    if not evidence:
        return {
            "success": False,
            "error": "Evidence codes list cannot be empty. Provide at least one ACMG evidence code.",
        }

    if not summary or len(summary) < 20:
        return {
            "success": False,
            "error": "Summary must be at least 20 characters with a meaningful explanation.",
        }

    return {
        "success": True,
        "classification": classification,
        "evidence_codes": evidence,
        "summary": summary,
        "variant": variant,
        "confidence": confidence or "moderate",
        "is_terminal": True,
    }


# ═══ Tool Invocation Engine ═══════════════════════════════════════════════════


class ToolRegistry:
    """Registry of available agent tools with invocation support.

    Provides tool lookup by name, schema generation for LLM prompts,
    and safe invocation with error handling and timing.

    Parameters
    ----------
    kb : KnowledgeBase, optional
        Shared knowledge base instance. If None, each tool creates its own.
    """

    def __init__(self, kb: Optional[KnowledgeBase] = None) -> None:
        self._kb = kb or KnowledgeBase()
        self._tools: dict[str, ToolDefinition] = {}
        self._invocation_log: list[ToolResult] = []
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register the 5 standard agent tools."""

        # Tool 1: query_clinvar
        self._tools["query_clinvar"] = ToolDefinition(
            name="query_clinvar",
            description=(
                "Look up ClinVar clinical significance for a genomic variant. "
                "Returns the variant's pathogenicity classification, review status "
                "(star rating), associated conditions, and HGVS nomenclature. "
                "Use this to check if a variant has been previously classified."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "chrom": {
                        "type": "string",
                        "description": "Chromosome (e.g., 'chr20')",
                    },
                    "pos": {
                        "type": "integer",
                        "description": "1-based genomic position",
                    },
                    "ref": {
                        "type": "string",
                        "description": "Reference allele (e.g., 'G')",
                    },
                    "alt": {
                        "type": "string",
                        "description": "Alternate allele (e.g., 'A')",
                    },
                },
                "required": ["chrom", "pos", "ref", "alt"],
            },
            function=lambda **kwargs: _query_clinvar(**kwargs, _kb=self._kb),
        )

        # Tool 2: query_gnomad
        self._tools["query_gnomad"] = ToolDefinition(
            name="query_gnomad",
            description=(
                "Look up population allele frequency from gnomAD for a genomic variant. "
                "Returns global allele frequency, population-maximum frequency, homozygote "
                "count, and ACMG frequency-based evidence codes (BA1/BS1/PM2). "
                "Use this to assess how common a variant is in the general population."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "chrom": {
                        "type": "string",
                        "description": "Chromosome (e.g., 'chr20')",
                    },
                    "pos": {
                        "type": "integer",
                        "description": "1-based genomic position",
                    },
                    "ref": {
                        "type": "string",
                        "description": "Reference allele (e.g., 'G')",
                    },
                    "alt": {
                        "type": "string",
                        "description": "Alternate allele (e.g., 'A')",
                    },
                },
                "required": ["chrom", "pos", "ref", "alt"],
            },
            function=lambda **kwargs: _query_gnomad(**kwargs, _kb=self._kb),
        )

        # Tool 3: query_gene_info
        self._tools["query_gene_info"] = ToolDefinition(
            name="query_gene_info",
            description=(
                "Get gene function, disease associations, and genomic coordinates. "
                "Returns the gene's description, associated conditions from ClinVar, "
                "and a summary of known variant classifications for that gene. "
                "Use this to understand the disease relevance of the gene a variant is in."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "gene_symbol": {
                        "type": "string",
                        "description": "HGNC gene symbol (e.g., 'PRNP', 'JAG1')",
                    },
                },
                "required": ["gene_symbol"],
            },
            function=lambda **kwargs: _query_gene_info(**kwargs, _kb=self._kb),
        )

        # Tool 4: classify_acmg
        self._tools["classify_acmg"] = ToolDefinition(
            name="classify_acmg",
            description=(
                "Apply ACMG/AMP 2015 combining rules to a list of evidence codes to "
                "determine the pathogenicity classification. Input is a list of evidence "
                "codes you have gathered (e.g., ['PS1', 'PM2', 'PP3']). Returns the "
                "classification (Pathogenic/Likely Pathogenic/VUS/Likely Benign/Benign), "
                "the specific rule matched, and confidence level. "
                "Call this AFTER gathering evidence from ClinVar and gnomAD."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "evidence_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of ACMG evidence codes gathered for this variant. "
                            "Codes: PVS1, PS1-PS4, PM1-PM6, PP1-PP5 (pathogenic); "
                            "BA1, BS1-BS4, BP1-BP7 (benign)."
                        ),
                    },
                },
                "required": ["evidence_codes"],
            },
            function=lambda **kwargs: _classify_acmg(**kwargs, _kb=self._kb),
        )

        # Tool 5: final_answer
        self._tools["final_answer"] = ToolDefinition(
            name="final_answer",
            description=(
                "Submit the final variant interpretation. This terminates the agent loop. "
                "You MUST provide: (1) the classification, (2) evidence codes supporting it, "
                "and (3) a plain-language summary explaining the reasoning. "
                "Call this ONLY after you have gathered sufficient evidence and applied "
                "the ACMG combining rules."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "classification": {
                        "type": "string",
                        "enum": [
                            "Pathogenic",
                            "Likely Pathogenic",
                            "Uncertain Significance",
                            "Likely Benign",
                            "Benign",
                        ],
                        "description": "ACMG/AMP pathogenicity classification",
                    },
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of ACMG evidence codes supporting this classification",
                    },
                    "summary": {
                        "type": "string",
                        "description": (
                            "Plain-language summary (50-200 words) explaining the "
                            "evidence and reasoning for this classification"
                        ),
                    },
                    "variant": {
                        "type": "string",
                        "description": "Variant identifier (e.g., 'chr20:4699605 G>A PRNP p.Glu200Lys')",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "moderate", "low"],
                        "description": "Confidence in the classification",
                    },
                },
                "required": ["classification", "evidence", "summary"],
            },
            function=_final_answer,
        )

    @property
    def tools(self) -> dict[str, ToolDefinition]:
        """Return all registered tools."""
        return self._tools

    @property
    def invocation_log(self) -> list[ToolResult]:
        """Return the full invocation log for provenance/tracing."""
        return self._invocation_log

    def get_tool_schemas(self, format: str = "openai") -> list[dict]:
        """Get all tool schemas in the specified format.

        Parameters
        ----------
        format : str
            Either 'openai' or 'anthropic'.
        """
        if format == "anthropic":
            return [t.to_anthropic_schema() for t in self._tools.values()]
        return [t.to_schema() for t in self._tools.values()]

    def invoke(self, tool_name: str, arguments: dict) -> ToolResult:
        """Invoke a tool by name with the given arguments.

        Handles validation, execution timing, error catching, and logging.

        Parameters
        ----------
        tool_name : str
            Name of the tool to invoke.
        arguments : dict
            Arguments to pass to the tool function.

        Returns
        -------
        ToolResult
            Structured result with output, timing, and error info.
        """
        if tool_name not in self._tools:
            result = ToolResult(
                tool_name=tool_name,
                input_args=arguments,
                output={"error": f"Unknown tool: {tool_name}"},
                success=False,
                error=f"Tool '{tool_name}' not found. Available: {list(self._tools.keys())}",
            )
            self._invocation_log.append(result)
            return result

        tool = self._tools[tool_name]
        start = time.perf_counter()

        try:
            output = tool.function(**arguments)
            duration_ms = (time.perf_counter() - start) * 1000

            result = ToolResult(
                tool_name=tool_name,
                input_args=arguments,
                output=output,
                success=True,
                duration_ms=duration_ms,
            )

        except TypeError as e:
            duration_ms = (time.perf_counter() - start) * 1000
            result = ToolResult(
                tool_name=tool_name,
                input_args=arguments,
                output={"error": f"Invalid arguments: {e}"},
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(f"Tool '{tool_name}' failed: {e}")
            result = ToolResult(
                tool_name=tool_name,
                input_args=arguments,
                output={"error": f"Tool execution failed: {e}"},
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )

        self._invocation_log.append(result)
        logger.info(
            f"Tool invoked: {tool_name} | success={result.success} | "
            f"duration={result.duration_ms:.1f}ms"
        )
        return result

    def reset_log(self) -> None:
        """Clear the invocation log."""
        self._invocation_log.clear()

    def close(self) -> None:
        """Close the underlying knowledge base connection."""
        self._kb.close()
