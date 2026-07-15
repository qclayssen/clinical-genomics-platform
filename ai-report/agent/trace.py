"""Agent trace and provenance for full observability.

Records the agent's reasoning trace for reproducibility, debugging,
and clinical audit. Integrates with the existing DynamoDB AUDIT record
pattern from the platform.

The trace captures every step: thoughts, tool calls, observations, errors,
and the final answer — providing a complete audit trail of how a
classification was reached.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .react import InterpretationResult, TraceStep


# ═══ Agent Trace ══════════════════════════════════════════════════════════════


@dataclass
class AgentTrace:
    """Complete trace of an agent interpretation run.

    Attributes
    ----------
    run_id : str
        Unique run identifier.
    steps : list[TraceStep]
        All reasoning steps (thoughts, actions, observations, answers).
    total_tokens : int
        Total tokens consumed across all LLM calls.
    wall_time_ms : float
        Total wall-clock time in milliseconds.
    backend_used : str
        LLM backend that produced the trace.
    fallback_triggered : bool
        Whether the deterministic fallback was used.
    variant : str
        String representation of the variant being interpreted.
    classification : str
        Final classification result.
    evidence_codes : list[str]
        Evidence codes supporting the classification.
    error : str or None
        Error message if the agent failed.
    """

    run_id: str = ""
    steps: list[TraceStep] = field(default_factory=list)
    total_tokens: int = 0
    wall_time_ms: float = 0.0
    backend_used: str = ""
    fallback_triggered: bool = False
    variant: str = ""
    classification: str = ""
    evidence_codes: list[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "variant": self.variant,
            "classification": self.classification,
            "evidence_codes": self.evidence_codes,
            "backend_used": self.backend_used,
            "fallback_triggered": self.fallback_triggered,
            "total_tokens": self.total_tokens,
            "wall_time_ms": round(self.wall_time_ms, 2),
            "n_steps": len(self.steps),
            "n_tool_calls": sum(1 for s in self.steps if s.step_type == "action"),
            "n_errors": sum(1 for s in self.steps if s.step_type == "error"),
            "error": self.error,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_result(cls, result: InterpretationResult, run_id: str = "") -> "AgentTrace":
        """Create an AgentTrace from an InterpretationResult."""
        return cls(
            run_id=run_id,
            steps=result.trace,
            total_tokens=result.total_tokens,
            wall_time_ms=result.wall_time_ms,
            backend_used=result.backend_used,
            fallback_triggered=result.fallback_triggered,
            variant=str(result.variant),
            classification=result.classification,
            evidence_codes=result.evidence_codes,
            error=result.error,
        )


@dataclass
class RunTrace:
    """Trace for an entire interpretation run (multiple variants).

    Captures the full run metadata plus per-variant traces.
    """

    run_id: str
    variant_traces: list[AgentTrace] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""
    total_wall_time_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_wall_time_ms": round(self.total_wall_time_ms, 2),
            "n_variants": len(self.variant_traces),
            "provenance": self.provenance,
            "summary": {
                "total_tool_calls": sum(t.to_dict()["n_tool_calls"] for t in self.variant_traces),
                "total_tokens": sum(t.total_tokens for t in self.variant_traces),
                "any_fallback": any(t.fallback_triggered for t in self.variant_traces),
                "any_errors": any(t.error for t in self.variant_traces),
                "classifications": self._classification_summary(),
            },
            "variant_traces": [t.to_dict() for t in self.variant_traces],
        }

    def _classification_summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self.variant_traces:
            counts[t.classification] = counts.get(t.classification, 0) + 1
        return counts


# ═══ Trace I/O ════════════════════════════════════════════════════════════════


def save_trace(trace: RunTrace, output_dir: str) -> str:
    """Save the run trace to a JSON file.

    Parameters
    ----------
    trace : RunTrace
        The complete run trace.
    output_dir : str
        Directory to write the trace file.

    Returns
    -------
    str
        Path to the saved trace file.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    trace_path = os.path.join(output_dir, "agent_trace.json")

    with open(trace_path, "w") as f:
        json.dump(trace.to_dict(), f, indent=2)

    return trace_path


def load_trace(trace_path: str) -> dict:
    """Load a saved trace from disk."""
    with open(trace_path) as f:
        return json.load(f)


# ═══ Provenance Stamp ═════════════════════════════════════════════════════════


def build_provenance_stamp(
    backend_used: str,
    run_id: str = "",
    vcf_path: str = "",
    metrics_path: str = "",
    kb_path: Optional[str] = None,
) -> dict:
    """Build a provenance stamp for the interpretation run.

    Includes: agent version, LLM model, tool versions, knowledge base checksum.

    Parameters
    ----------
    backend_used : str
        LLM backend identifier.
    run_id : str
        Pipeline run ID.
    vcf_path : str
        Path to source VCF.
    metrics_path : str
        Path to metrics JSON.
    kb_path : str, optional
        Path to knowledge base SQLite. Auto-detected if None.

    Returns
    -------
    dict
        Provenance stamp for inclusion in reports and audit records.
    """
    from . import __version__ as agent_version

    # Compute KB checksum if available
    kb_checksum = ""
    if kb_path is None:
        kb_path_resolved = str(
            Path(__file__).resolve().parent / "data" / "chr20_knowledge.db"
        )
    else:
        kb_path_resolved = kb_path

    if os.path.exists(kb_path_resolved):
        kb_checksum = _file_sha256(kb_path_resolved)

    return {
        "agent_version": agent_version,
        "backend": backend_used,
        "knowledge_base": {
            "path": os.path.basename(kb_path_resolved),
            "sha256": kb_checksum,
            "version": "1.0.0",
            "region": "chr20",
        },
        "acmg_guidelines": "ACMG/AMP 2015 (Richards et al., Genet Med)",
        "run_id": run_id,
        "inputs": {
            "vcf": vcf_path,
            "metrics": metrics_path,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _file_sha256(path: str) -> str:
    """Compute SHA-256 checksum of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


# ═══ Audit Record (DynamoDB integration) ══════════════════════════════════════


def build_audit_record(
    run_id: str,
    n_variants: int,
    classifications: dict[str, int],
    backend_used: str,
    wall_time_ms: float,
    any_fallback: bool = False,
) -> dict:
    """Build an INTERPRETATION_COMPLETED audit record.

    Compatible with the existing DynamoDB audit trail pattern
    (see lambdas/shared/audit.py).

    Parameters
    ----------
    run_id : str
        Pipeline run identifier.
    n_variants : int
        Number of variants interpreted.
    classifications : dict[str, int]
        Classification counts.
    backend_used : str
        LLM backend used.
    wall_time_ms : float
        Total execution time.
    any_fallback : bool
        Whether any variant triggered the deterministic fallback.

    Returns
    -------
    dict
        Audit record ready for DynamoDB insertion.
    """
    return {
        "run_id": run_id,
        "record_type": "AUDIT",
        "action": "INTERPRETATION_COMPLETED",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "details": {
            "n_variants": n_variants,
            "classifications": classifications,
            "backend_used": backend_used,
            "wall_time_ms": round(wall_time_ms, 2),
            "fallback_triggered": any_fallback,
        },
    }


# ═══ Pretty Printing ══════════════════════════════════════════════════════════


def pretty_print_trace(trace: AgentTrace) -> str:
    """Format an agent trace for human-readable display.

    Shows the reasoning chain: Thought → Action → Observation → Answer.
    """
    lines: list[str] = []
    lines.append(f"═══ Agent Trace: {trace.variant} ═══")
    lines.append(f"  Backend: {trace.backend_used}")
    lines.append(f"  Classification: {trace.classification}")
    lines.append(f"  Evidence: {', '.join(trace.evidence_codes)}")
    lines.append(f"  Wall time: {trace.wall_time_ms:.1f}ms")
    lines.append(f"  Tokens: {trace.total_tokens}")
    lines.append(f"  Fallback: {trace.fallback_triggered}")
    if trace.error:
        lines.append(f"  Error: {trace.error}")
    lines.append("")

    for i, step in enumerate(trace.steps):
        prefix = f"  [{i+1:>2}]"
        if step.step_type == "thought":
            lines.append(f"{prefix} THOUGHT: {step.content}")
        elif step.step_type == "action":
            args_str = json.dumps(step.tool_input) if step.tool_input else ""
            lines.append(f"{prefix} ACTION:  {step.tool_name}({args_str})")
        elif step.step_type == "observation":
            # Truncate long observations
            content = step.content
            if len(content) > 120:
                content = content[:117] + "..."
            lines.append(f"{prefix} OBSERVE: {content}")
        elif step.step_type == "answer":
            lines.append(f"{prefix} ANSWER:  {step.content[:200]}")
        elif step.step_type == "error":
            lines.append(f"{prefix} ERROR:   {step.content}")

    lines.append("")
    return "\n".join(lines)


def pretty_print_run_trace(run_trace: RunTrace) -> str:
    """Format a full run trace for display."""
    lines: list[str] = []
    lines.append(f"{'═' * 60}")
    lines.append(f"Agent Run Trace: {run_trace.run_id}")
    lines.append(f"{'═' * 60}")
    lines.append(f"  Started:  {run_trace.started_at}")
    lines.append(f"  Completed: {run_trace.completed_at}")
    lines.append(f"  Duration: {run_trace.total_wall_time_ms:.1f}ms")
    lines.append(f"  Variants: {len(run_trace.variant_traces)}")
    lines.append("")

    for vt in run_trace.variant_traces:
        lines.append(pretty_print_trace(vt))

    return "\n".join(lines)
