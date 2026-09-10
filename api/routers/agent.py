"""Variant Interpretation Assistant endpoint.

This exposes the platform's *existing* agentic variant interpreter
(`ai-report/agent/` — ReAct loop + tool use + ACMG/AMP combining rules,
see ADR-0014) over REST for the first time; previously it was reachable only
via the CLI (`ai-report/agent/interpret.py`) or the Streamlit demo
(`demo/pages/interpret.py`). No new agent, tool, or classification logic is
implemented here — this route is a thin adapter, matching the deterministic
interpreter is the default policy `demo/pages/interpret.py` already
documents: no LLM, no network, no setup, so the route behaves the same on a
laptop and in a container.

Sign-off deliberately reuses the existing insert-only
`POST /runs/{run_id}/review-decisions` (see api/routers/runs.py, ADR-0019)
rather than adding a second endpoint/table — `variant_key` ("chrom:pos:ref>alt",
from `agent.review_store.variant_key`) is what links a decision back to the
variant interpreted here. A second, competing sign-off mechanism would
fragment the one audit trail this platform already has.

Two additions on top of that thin adapter (ADR-0028):

- An opt-in `backend` field selects among the LLM backends `agent/llm.py`
  already supports (`ollama`, `openai`, `anthropic`, `azure_foundry`,
  `bedrock`) to drive the real `ReActAgent` instead of the deterministic
  default. If the agent can't complete cleanly on the chosen backend, it
  falls back to the deterministic interpreter — the same policy
  `ai-report/agent/interpret.py`'s CLI already uses, reused here rather
  than reinvented.
- `POST /agent/variant-review/fhir` accepts a (simplified) HL7 FHIR
  genomics `Observation` instead of discrete chrom/pos/ref/alt fields, via
  `agent.fhir_intake.variant_from_fhir_observation` — an EMR-shaped intake
  path alongside the manual form.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

# ai-report/ isn't a package root (see ai-report/agent/interpret.py and
# demo/pages/interpret.py, which do the same sys.path insertion) — `agent`
# below is ai-report/agent, imported as a bare top-level module.
_AI_REPORT_DIR = Path(__file__).resolve().parents[2] / "ai-report"
if str(_AI_REPORT_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_REPORT_DIR))

from agent.deterministic import DeterministicInterpreter  # noqa: E402
from agent.fhir_intake import FhirIntakeError, variant_from_fhir_observation  # noqa: E402
from agent.llm import create_backend  # noqa: E402
from agent.react import ReActAgent, Variant, enforce_safety_constraints  # noqa: E402
from agent.report import INTERPRETATION_BANNER, build_report, enforce_report_guardrails  # noqa: E402
from agent.review_store import variant_key  # noqa: E402

router = APIRouter(prefix="/agent", tags=["agent"])

_KNOWN_BACKENDS = {"deterministic", "ollama", "openai", "anthropic", "azure_foundry", "azure", "bedrock"}


class VariantReviewRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "chrom": "chr20",
            "pos": 4699605,
            "ref": "G",
            "alt": "A",
            "gene": "PRNP",
            "genotype": "heterozygous",
            "run_id": "run_2026_0301_a",
        }]
    })

    chrom: str
    pos: int
    ref: str
    alt: str
    gene: str = ""
    genotype: str = Field("heterozygous", description="Zygosity, e.g. heterozygous/homozygous")
    run_id: str = Field(
        ..., description="An existing pipeline run id (see GET /runs) to tie this interpretation and any sign-off to"
    )
    backend: str = Field(
        "deterministic",
        description=(
            "One of deterministic|ollama|openai|anthropic|azure_foundry|bedrock. "
            "Non-deterministic backends need their own credentials configured "
            "(see ai-report/agent/llm.py) and fall back to deterministic on failure."
        ),
    )


class FhirVariantReviewRequest(BaseModel):
    """Same review, but the variant comes from a FHIR Observation instead of
    discrete fields — see `agent.fhir_intake` for exactly which components
    are read."""

    resource: dict[str, Any] = Field(..., description="A FHIR Observation resource (see agent.fhir_intake)")
    run_id: str
    backend: str = "deterministic"


# Step types whose `content` is free text the LLM wrote. The advice-scrub
# (ADR-0008) has to reach these too: it used to be applied only to the final
# summary, so on a live backend the model's own prose — including any
# treatment language — was rendered verbatim in the UI's trace panel.
# `action`/`observation` steps are deliberately excluded: their content is a
# tool name, its arguments, or curated knowledge-base output, none of which the
# model authors, and scrubbing them would corrupt the audit trail.
_MODEL_AUTHORED_STEP_TYPES = frozenset({"thought", "answer", "error"})


def _scrubbed_trace_steps(trace) -> tuple[list["AgentTraceStep"], list[str]]:
    """Serialise the trace, scrubbing advice language out of model-written steps.

    Returns the steps plus any violations found, so a scrub in the trace is
    surfaced to the reviewer rather than silently applied.
    """
    steps: list[AgentTraceStep] = []
    violations: list[str] = []
    for step in trace:
        payload = step.to_dict()
        if payload.get("type") in _MODEL_AUTHORED_STEP_TYPES and payload.get("content"):
            scrubbed, found = enforce_safety_constraints(payload["content"])
            payload["content"] = scrubbed
            violations.extend(f"Trace step ({payload['type']}): {v}" for v in found)
        steps.append(AgentTraceStep(**payload))
    return steps, violations


class AgentTraceStep(BaseModel):
    """One Thought/Action/Observation step from the ReAct-style trace.

    Field names mirror `agent.react.TraceStep.to_dict()` exactly, so the
    detailed per-tool-call trace is passed through for the transparency this
    feature is built around — never collapsed or summarized. The one
    modification is the ADR-0008 advice-scrub on model-authored steps; see
    `_scrubbed_trace_steps`.
    """

    type: str
    content: str
    timestamp: float = 0.0
    tool_name: str | None = None
    tool_input: dict | None = None
    tool_output: dict | None = None
    duration_ms: float | None = None


class VariantAssessment(BaseModel):
    run_id: str
    variant_key: str
    chrom: str
    pos: int
    ref: str
    alt: str
    gene: str
    genotype: str
    classification: str
    evidence_codes: list[str]
    confidence: str
    summary: str
    citations: list[str]
    banner: str
    backend_used: str
    agent_trace: list[AgentTraceStep]
    provenance: dict
    guardrail_violations: list[str] = Field(
        default_factory=list, description="Empty when the report is fully guardrail-compliant"
    )


def _run_interpretation(variant: Variant, backend_name: str):
    """Run `variant` through the deterministic interpreter or a real
    ReActAgent backend, mirroring `ai-report/agent/interpret.py`'s CLI
    policy exactly: deterministic is default and needs nothing configured;
    any other backend runs the real agent and falls back to deterministic
    if it can't complete cleanly (loop detected, backend unavailable, etc.),
    keeping the agent's partial trace prepended to the fallback's.
    """
    name = backend_name.lower().strip()
    if name not in _KNOWN_BACKENDS:
        raise HTTPException(status_code=422, detail=f"Unknown backend '{backend_name}'. One of: {sorted(_KNOWN_BACKENDS)}")

    if name == "deterministic":
        return DeterministicInterpreter().run(variant)

    llm_backend = create_backend(name)
    react_agent = ReActAgent(backend=llm_backend)
    try:
        result = react_agent.run(variant)
    finally:
        react_agent.close()

    if result.fallback_triggered:
        fallback_result = DeterministicInterpreter().run(variant)
        fallback_result.trace = result.trace + fallback_result.trace
        return fallback_result
    return result


def _to_assessment(variant: Variant, run_id: str, result) -> VariantAssessment:
    report = build_report([result], backend_used=result.backend_used, run_id=run_id)
    violations = enforce_report_guardrails(report)
    interpretation = report.variants[0]
    trace_steps, trace_violations = _scrubbed_trace_steps(result.trace)
    violations = violations + trace_violations

    return VariantAssessment(
        run_id=run_id,
        variant_key=variant_key(variant.chrom, variant.pos, variant.ref, variant.alt),
        chrom=variant.chrom,
        pos=variant.pos,
        ref=variant.ref,
        alt=variant.alt,
        gene=variant.gene,
        genotype=variant.genotype,
        classification=interpretation.classification,
        evidence_codes=interpretation.evidence_codes,
        confidence=interpretation.confidence,
        summary=interpretation.summary,
        citations=interpretation.citations,
        banner=INTERPRETATION_BANNER,
        backend_used=result.backend_used,
        agent_trace=trace_steps,
        provenance=report.provenance,
        guardrail_violations=violations,
    )


@router.post(
    "/variant-review",
    response_model=VariantAssessment,
    status_code=201,
    summary="Run the existing agentic variant interpreter (ADR-0014) on a single variant",
)
def create_variant_review(query: VariantReviewRequest) -> VariantAssessment:
    variant = Variant(
        chrom=query.chrom,
        pos=query.pos,
        ref=query.ref,
        alt=query.alt,
        gene=query.gene,
        genotype=query.genotype,
    )
    result = _run_interpretation(variant, query.backend)
    return _to_assessment(variant, query.run_id, result)


@router.post(
    "/variant-review/fhir",
    response_model=VariantAssessment,
    status_code=201,
    summary="Same as /variant-review, but the variant comes from a FHIR genomics Observation",
)
def create_variant_review_from_fhir(query: FhirVariantReviewRequest) -> VariantAssessment:
    try:
        variant = variant_from_fhir_observation(query.resource)
    except FhirIntakeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    result = _run_interpretation(variant, query.backend)
    return _to_assessment(variant, query.run_id, result)
