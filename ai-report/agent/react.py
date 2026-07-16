"""ReAct agent loop for variant interpretation.

Implements the core Thought → Action → Observation loop with:
- Tool dispatch via ToolRegistry
- Loop detection (same tool+args called twice → force fallback)
- Max iteration limit (default 10 per variant)
- Clinical safety constraint enforcement
- Token budget tracking
- Graceful fallback to deterministic interpretation on failure
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .llm import LLMBackend, Message, ToolCall, create_backend
from .tools import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


# ═══ Data Types ═══════════════════════════════════════════════════════════════


@dataclass
class Variant:
    """A genomic variant to interpret."""

    chrom: str
    pos: int
    ref: str
    alt: str
    qual: float = 0.0
    filter_status: str = "PASS"
    genotype: str = ""
    gene: str = ""

    def to_dict(self) -> dict:
        return {
            "chrom": self.chrom,
            "pos": self.pos,
            "ref": self.ref,
            "alt": self.alt,
            "qual": self.qual,
            "filter": self.filter_status,
            "genotype": self.genotype,
            "gene": self.gene,
        }

    def __str__(self) -> str:
        gene_str = f" ({self.gene})" if self.gene else ""
        return f"{self.chrom}:{self.pos} {self.ref}>{self.alt}{gene_str}"


@dataclass
class TraceStep:
    """A single step in the agent's reasoning trace."""

    step_type: str  # 'thought', 'action', 'observation', 'answer', 'error'
    content: str
    timestamp: float = 0.0
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
    tool_output: dict = field(default_factory=dict)
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        d = {
            "type": self.step_type,
            "content": self.content,
            "timestamp": self.timestamp,
        }
        if self.tool_name:
            d["tool_name"] = self.tool_name
        if self.tool_input:
            d["tool_input"] = self.tool_input
        if self.tool_output:
            d["tool_output"] = self.tool_output
        if self.duration_ms:
            d["duration_ms"] = self.duration_ms
        return d


@dataclass
class InterpretationResult:
    """Result of interpreting a single variant."""

    variant: Variant
    classification: str = "Uncertain Significance"
    evidence_codes: list[str] = field(default_factory=list)
    summary: str = ""
    confidence: str = "low"
    trace: list[TraceStep] = field(default_factory=list)
    backend_used: str = ""
    fallback_triggered: bool = False
    total_tokens: int = 0
    wall_time_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "variant": self.variant.to_dict(),
            "classification": self.classification,
            "evidence_codes": self.evidence_codes,
            "summary": self.summary,
            "confidence": self.confidence,
            "trace": [s.to_dict() for s in self.trace],
            "backend_used": self.backend_used,
            "fallback_triggered": self.fallback_triggered,
            "total_tokens": self.total_tokens,
            "wall_time_ms": self.wall_time_ms,
            "error": self.error,
        }


# ═══ Safety Constraints ═══════════════════════════════════════════════════════

# Phrases that indicate treatment/clinical management recommendations
_TREATMENT_PATTERNS = [
    r"\bwe recommend\b",
    r"\bshould (?:take|start|stop|begin|consider)\b",
    r"\btreat(?:ment|ed)?\s+with\b",
    r"\bprescri(?:be|ption)\b",
    r"\bthis (?:confirms|establishes) (?:a |the )?diagnos(?:is|e)\b",
    r"\btherapy\b",
    r"\bmedication\b",
    r"\bclinical management\b",
]

_TREATMENT_RE = re.compile("|".join(_TREATMENT_PATTERNS), re.IGNORECASE)


def enforce_safety_constraints(text: str) -> tuple[str, list[str]]:
    """Enforce clinical safety constraints on agent output.

    Returns
    -------
    tuple[str, list[str]]
        (scrubbed_text, list_of_violations_found)
    """
    violations: list[str] = []

    # Check for treatment recommendations
    matches = _TREATMENT_RE.findall(text)
    if matches:
        violations.append(f"Treatment language detected: {matches}")
        text = _TREATMENT_RE.sub("[REVIEW REQUIRED]", text)

    return text, violations


# ═══ ReAct Agent ══════════════════════════════════════════════════════════════


class ReActAgent:
    """ReAct-style variant interpretation agent.

    Implements Thought → Action → Observation loop with safety guardrails.

    Parameters
    ----------
    backend : LLMBackend, optional
        LLM backend to use. If None, creates from AGENT_LLM_BACKEND env var.
    max_iterations : int
        Maximum tool calls per variant (prevents infinite loops). Default: 10.
    max_tokens_per_run : int
        Token budget per agent run. Default: 4096.
    """

    def __init__(
        self,
        backend: Optional[LLMBackend] = None,
        max_iterations: int = 10,
        max_tokens_per_run: int = 4096,
    ) -> None:
        self._backend = backend or create_backend()
        self._max_iterations = max_iterations
        self._max_tokens = max_tokens_per_run
        self._tool_registry = ToolRegistry()
        self._system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load the system prompt from the prompts directory."""
        prompt_path = _PROMPTS_DIR / "system.md"
        if prompt_path.exists():
            return prompt_path.read_text()
        # Fallback minimal prompt
        return (
            "You are a variant interpretation agent. Use the available tools "
            "to gather evidence and classify variants using ACMG/AMP criteria. "
            "Always call final_answer when done."
        )

    def run(self, variant: Variant) -> InterpretationResult:
        """Interpret a single variant using the ReAct loop.

        Parameters
        ----------
        variant : Variant
            The variant to interpret.

        Returns
        -------
        InterpretationResult
            Classification result with full reasoning trace.
        """
        start_time = time.perf_counter()
        trace: list[TraceStep] = []
        total_tokens = 0

        # Build initial messages
        messages: list[Message] = [
            Message(role="system", content=self._system_prompt),
            Message(role="user", content=self._format_variant_prompt(variant)),
        ]

        # Track tool calls for loop detection
        call_history: list[tuple[str, str]] = []  # (tool_name, args_hash)

        result = InterpretationResult(
            variant=variant,
            backend_used=self._backend.model_id,
        )

        try:
            for iteration in range(self._max_iterations):
                # Get LLM response
                step_start = time.perf_counter()
                try:
                    response = self._backend.generate(
                        messages=messages,
                        tools=self._tool_registry.get_tool_schemas("openai"),
                        temperature=0.1,
                        max_tokens=min(1024, self._max_tokens - total_tokens),
                    )
                except (ConnectionError, ValueError, RuntimeError) as e:
                    trace.append(TraceStep(
                        step_type="error",
                        content=f"LLM backend error: {e}",
                        timestamp=time.time(),
                    ))
                    result.fallback_triggered = True
                    result.error = f"LLM error at iteration {iteration}: {e}"
                    break

                step_duration = (time.perf_counter() - step_start) * 1000

                # Track tokens
                usage = response.usage
                total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

                # Record thought
                if response.content:
                    trace.append(TraceStep(
                        step_type="thought",
                        content=response.content,
                        timestamp=time.time(),
                        duration_ms=step_duration,
                    ))

                # No tool calls = agent wants to stop (shouldn't happen without final_answer)
                if not response.has_tool_calls:
                    trace.append(TraceStep(
                        step_type="error",
                        content="Agent stopped without calling final_answer",
                        timestamp=time.time(),
                    ))
                    result.fallback_triggered = True
                    result.error = "Agent stopped without final_answer"
                    break

                # Process tool calls — collect all results before appending
                # to conversation to avoid malformed history with multi-tool
                # responses (one assistant message with N tool calls, then N
                # tool-result messages).
                tool_results_batch: list[tuple["ToolCall", ToolResult]] = []

                for tool_call in response.tool_calls:
                    # Loop detection
                    args_hash = json.dumps(tool_call.arguments, sort_keys=True)
                    call_key = (tool_call.name, args_hash)

                    if call_key in call_history:
                        trace.append(TraceStep(
                            step_type="error",
                            content=f"Loop detected: {tool_call.name} called with same args twice",
                            timestamp=time.time(),
                        ))
                        result.fallback_triggered = True
                        result.error = f"Loop detected at iteration {iteration}"
                        break

                    call_history.append(call_key)

                    # Invoke tool
                    trace.append(TraceStep(
                        step_type="action",
                        content=f"Calling {tool_call.name}",
                        timestamp=time.time(),
                        tool_name=tool_call.name,
                        tool_input=tool_call.arguments,
                    ))

                    tool_result = self._tool_registry.invoke(
                        tool_call.name, tool_call.arguments
                    )

                    trace.append(TraceStep(
                        step_type="observation",
                        content=json.dumps(tool_result.output),
                        timestamp=time.time(),
                        tool_name=tool_call.name,
                        tool_output=tool_result.output,
                        duration_ms=tool_result.duration_ms,
                    ))

                    tool_results_batch.append((tool_call, tool_result))

                    # Check if this is a terminal tool call (final_answer)
                    if tool_call.name == "final_answer" and tool_result.success:
                        output = tool_result.output
                        if output.get("is_terminal") and output.get("success"):
                            # Apply safety constraints to summary
                            summary = output.get("summary", "")
                            summary, violations = enforce_safety_constraints(summary)

                            if violations:
                                trace.append(TraceStep(
                                    step_type="error",
                                    content=f"Safety violations scrubbed: {violations}",
                                    timestamp=time.time(),
                                ))

                            result.classification = output["classification"]
                            result.evidence_codes = output["evidence_codes"]
                            result.summary = summary
                            result.confidence = output.get("confidence", "moderate")
                            result.trace = trace
                            result.total_tokens = total_tokens
                            result.wall_time_ms = (time.perf_counter() - start_time) * 1000
                            return result

                # Append conversation history correctly: one assistant message
                # carrying all tool calls, then one tool-result message per call.
                if tool_results_batch and not result.fallback_triggered:
                    messages.append(Message(
                        role="assistant",
                        content=response.content or "",
                        tool_calls=[tc for tc, _ in tool_results_batch],
                    ))
                    for tc, tr in tool_results_batch:
                        messages.append(Message(
                            role="tool",
                            content=json.dumps(tr.output),
                            tool_call_id=tc.id,
                            name=tc.name,
                        ))

                # Check if loop was triggered
                if result.fallback_triggered:
                    break

                # Token budget check
                if total_tokens >= self._max_tokens:
                    trace.append(TraceStep(
                        step_type="error",
                        content=f"Token budget exhausted ({total_tokens}/{self._max_tokens})",
                        timestamp=time.time(),
                    ))
                    result.fallback_triggered = True
                    result.error = "Token budget exhausted"
                    break

            else:
                # Max iterations reached
                trace.append(TraceStep(
                    step_type="error",
                    content=f"Max iterations reached ({self._max_iterations})",
                    timestamp=time.time(),
                ))
                result.fallback_triggered = True
                result.error = f"Max iterations ({self._max_iterations}) reached"

        except Exception as e:
            trace.append(TraceStep(
                step_type="error",
                content=f"Unexpected error: {e}",
                timestamp=time.time(),
            ))
            result.fallback_triggered = True
            result.error = f"Unexpected error: {e}"
            logger.exception(f"Agent loop failed for {variant}")

        # If we reach here, the agent didn't produce a final answer
        result.trace = trace
        result.total_tokens = total_tokens
        result.wall_time_ms = (time.perf_counter() - start_time) * 1000
        return result

    def run_batch(self, variants: list[Variant]) -> list[InterpretationResult]:
        """Interpret a batch of variants sequentially.

        Parameters
        ----------
        variants : list[Variant]
            Variants to interpret.

        Returns
        -------
        list[InterpretationResult]
            Results for each variant (order preserved).
        """
        results = []
        for variant in variants:
            logger.info(f"Interpreting variant: {variant}")
            result = self.run(variant)
            results.append(result)
            # Reset tool registry log between variants
            self._tool_registry.reset_log()
        return results

    def close(self) -> None:
        """Close the tool registry and its underlying knowledge base connection."""
        self._tool_registry.close()

    def _format_variant_prompt(self, variant: Variant) -> str:
        """Format the variant as a user prompt for the agent."""
        parts = [
            "Please interpret the following variant:\n",
            f"  Chromosome: {variant.chrom}",
            f"  Position: {variant.pos}",
            f"  Reference allele: {variant.ref}",
            f"  Alternate allele: {variant.alt}",
        ]
        if variant.gene:
            parts.append(f"  Gene: {variant.gene}")
        if variant.genotype:
            parts.append(f"  Genotype: {variant.genotype}")
        if variant.qual > 0:
            parts.append(f"  Quality: {variant.qual}")
        if variant.filter_status:
            parts.append(f"  Filter: {variant.filter_status}")

        parts.append(
            "\nGather evidence from ClinVar, gnomAD, and gene annotations, "
            "then apply ACMG/AMP criteria to classify this variant."
        )

        # Also include as JSON for the deterministic backend
        parts.append(f"\n{json.dumps(variant.to_dict())}")

        return "\n".join(parts)
