"""LLM observability for the variant-interpretation agent (roadmap AI-8).

Per-LLM-call accounting that extends the existing agent trace
(`react.InterpretationResult` / `trace.AgentTrace`) rather than a parallel
trace: backend, model id, prompt/completion tokens, latency, and an
*estimated* cost from a small dated price table.

Honesty rules (ADR-0036):

- Token counts are recorded only when the backend reports them. A backend
  that returns no usage block yields ``None`` — never a guessed or zero-filled
  number. Aggregates count those calls separately (``n_calls_without_usage``)
  instead of silently treating them as zero.
- Cost is an **estimate** from ``PRICE_TABLE`` (list prices, dated
  ``PRICE_TABLE_AS_OF``). A model not in the table, or a call without token
  counts, has cost ``None``. Local backends (deterministic, Ollama) have no
  per-token charge and are priced at 0.0 — that is a fact about the backend,
  not an estimate of compute cost.
- No PHI and no prompt/completion text is ever recorded here: records hold
  counts, ids, and timings only. The trace's thought/observation steps keep
  their existing content (needed for clinical review), but nothing in this
  module — nor the OpenTelemetry spans or the ``agent_call_metrics`` table it
  feeds — carries prompt text, variant coordinates, or tool arguments.

Optional OpenTelemetry export: set ``AGENT_OTEL_ENABLED=1`` and install
``opentelemetry-api`` (plus an SDK/exporter of your choice). One span is
emitted per agent run, per LLM call, and per tool call. If the env var is
unset or the package is missing, every span helper is a no-op.
"""

from __future__ import annotations

import contextlib
import logging
import os
from dataclasses import asdict, dataclass
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

# ═══ Price table ══════════════════════════════════════════════════════════════
#
# USD per 1,000,000 tokens: (input, output). Reference *list* prices recorded
# on PRICE_TABLE_AS_OF for the backends' default models only. They were NOT
# fetched live and are not contract/discounted prices — treat every cost
# figure derived from them as an order-of-magnitude estimate, and verify
# against the provider's pricing page before relying on one. Update the date
# whenever a number changes; the date is stamped onto every persisted row
# (agent_call_metrics.price_table_version) so old estimates stay traceable.

PRICE_TABLE_AS_OF = "2026-09-24"
PRICE_TABLE_VERSION = f"list-prices-{PRICE_TABLE_AS_OF}"

PRICE_TABLE: dict[str, tuple[float, float]] = {
    # model_id (as produced by LLMBackend.model_id) → (input, output) per 1M
    "openai/gpt-4o-mini": (0.15, 0.60),
    "anthropic/claude-3-5-haiku-20241022": (0.80, 4.00),
    "bedrock/anthropic.claude-3-5-haiku-20241022-v1:0": (0.80, 4.00),
}

# Backends with no per-token charge. Cost 0.0 is exact for these, not estimated.
_LOCAL_BACKEND_PREFIXES = ("deterministic", "ollama/")


def estimate_cost_usd(
    model_id: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
) -> Optional[float]:
    """Estimated USD cost of one call, or ``None`` if it can't be estimated.

    ``None`` when the model is not in ``PRICE_TABLE`` or when either token
    count is unreported — a partial count would understate the cost.
    """
    if model_id.startswith(_LOCAL_BACKEND_PREFIXES):
        return 0.0
    prices = PRICE_TABLE.get(model_id)
    if prices is None or prompt_tokens is None or completion_tokens is None:
        return None
    in_price, out_price = prices
    return round((prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000, 8)


# ═══ Per-call record ══════════════════════════════════════════════════════════


@dataclass
class LLMCallRecord:
    """Counts/ids/timings for one LLM call. Deliberately holds no text."""

    iteration: int
    backend: str
    model_id: str
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    latency_ms: float
    estimated_cost_usd: Optional[float]
    stop_reason: str = ""
    n_tool_calls: int = 0
    trace_step_index: Optional[int] = None  # first TraceStep this call produced
    error: bool = False

    @property
    def total_tokens(self) -> Optional[int]:
        if self.prompt_tokens is None or self.completion_tokens is None:
            return None
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> dict:
        d = asdict(self)
        d["latency_ms"] = round(self.latency_ms, 2)
        d["total_tokens"] = self.total_tokens
        return d


def _usage_value(usage: Any, key: str) -> Optional[int]:
    """Read a token count from an LLMResponse.usage dict; None if unreported."""
    if not isinstance(usage, dict):
        return None
    value = usage.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def record_from_response(
    *,
    iteration: int,
    backend: str,
    model_id: str,
    response: Any,
    latency_ms: float,
    trace_step_index: Optional[int] = None,
) -> LLMCallRecord:
    """Build a record from an ``llm.LLMResponse`` (duck-typed)."""
    usage = getattr(response, "usage", None)
    prompt = _usage_value(usage, "input_tokens")
    completion = _usage_value(usage, "output_tokens")
    return LLMCallRecord(
        iteration=iteration,
        backend=backend,
        model_id=model_id,
        prompt_tokens=prompt,
        completion_tokens=completion,
        latency_ms=latency_ms,
        estimated_cost_usd=estimate_cost_usd(model_id, prompt, completion),
        stop_reason=getattr(response, "stop_reason", "") or "",
        n_tool_calls=len(getattr(response, "tool_calls", None) or []),
        trace_step_index=trace_step_index,
    )


def record_for_failed_call(
    *, iteration: int, backend: str, model_id: str, latency_ms: float,
    trace_step_index: Optional[int] = None,
) -> LLMCallRecord:
    """A call that raised: latency is real, tokens/cost are unknown."""
    return LLMCallRecord(
        iteration=iteration,
        backend=backend,
        model_id=model_id,
        prompt_tokens=None,
        completion_tokens=None,
        latency_ms=latency_ms,
        estimated_cost_usd=None,
        stop_reason="error",
        trace_step_index=trace_step_index,
        error=True,
    )


# ═══ Aggregation ══════════════════════════════════════════════════════════════


def _sum_or_none(values: list[Optional[float]]) -> Optional[float]:
    """Sum when every value is known; None if any is unknown. Empty → 0."""
    if any(v is None for v in values):
        return None
    return sum(v for v in values if v is not None)


def summarize_calls(calls: list[LLMCallRecord]) -> dict:
    """Aggregate per-call records into one usage summary.

    ``prompt_tokens``/``completion_tokens`` sum only the calls that reported
    usage; ``n_calls_without_usage`` says how many didn't, so a reader can
    tell an under-count from a true total. ``estimated_cost_usd`` is ``None``
    as soon as any call's cost is unknown — a partial sum would look like a
    complete one.
    """
    reported = [c for c in calls if c.prompt_tokens is not None and c.completion_tokens is not None]
    latencies = [c.latency_ms for c in calls]
    backends = sorted({c.backend for c in calls})
    models = sorted({c.model_id for c in calls})
    cost = _sum_or_none([c.estimated_cost_usd for c in calls])
    return {
        "n_llm_calls": len(calls),
        "n_failed_calls": sum(1 for c in calls if c.error),
        "n_calls_without_usage": len(calls) - len(reported),
        "prompt_tokens": sum(c.prompt_tokens for c in reported),  # type: ignore[misc]
        "completion_tokens": sum(c.completion_tokens for c in reported),  # type: ignore[misc]
        "total_latency_ms": round(sum(latencies), 2),
        "mean_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "max_latency_ms": round(max(latencies), 2) if latencies else None,
        "estimated_cost_usd": round(cost, 8) if cost is not None else None,
        "price_table_version": PRICE_TABLE_VERSION,
        "backends": backends,
        "models": models,
    }


def build_call_metrics_row(
    *,
    run_id: str,
    backend_used: str,
    fallback_triggered: bool,
    wall_time_ms: float,
    calls: list[LLMCallRecord],
) -> dict:
    """One ``agent_call_metrics`` row (db/migrations/0002) for one interpretation.

    Counts/ids only: no variant coordinates, no prompt or completion text.
    ``backend`` is the backend the agent was asked to use (first LLM call's
    backend), or ``backend_used`` when no LLM was called (deterministic path).
    """
    summary = summarize_calls(calls)
    backend = calls[0].backend if calls else backend_used
    model_id = calls[0].model_id if calls else backend_used
    has_usage = summary["n_llm_calls"] > summary["n_calls_without_usage"]
    all_usage = summary["n_calls_without_usage"] == 0
    return {
        "run_id": run_id,
        "backend": backend,
        "model_id": model_id,
        "n_llm_calls": summary["n_llm_calls"],
        "n_failed_calls": summary["n_failed_calls"],
        "n_calls_without_usage": summary["n_calls_without_usage"],
        # NULL (not 0) when no call reported usage — see module docstring.
        "prompt_tokens": summary["prompt_tokens"] if (has_usage or not calls) else None,
        "completion_tokens": summary["completion_tokens"] if (has_usage or not calls) else None,
        "usage_complete": all_usage,
        "llm_latency_ms": summary["total_latency_ms"],
        "wall_time_ms": round(wall_time_ms, 2),
        "estimated_cost_usd": summary["estimated_cost_usd"],
        "price_table_version": PRICE_TABLE_VERSION,
        "fallback_triggered": fallback_triggered,
    }


# ═══ Optional OpenTelemetry export ════════════════════════════════════════════

_OTEL_ENV = "AGENT_OTEL_ENABLED"
_TRACER_NAME = "cgp.variant_agent"


def otel_enabled() -> bool:
    return os.environ.get(_OTEL_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _get_tracer() -> Any:
    if not otel_enabled():
        return None
    try:
        from opentelemetry import trace as otel_trace  # type: ignore[import-not-found]
    except ImportError:
        logger.debug("%s set but opentelemetry is not installed; spans disabled", _OTEL_ENV)
        return None
    return otel_trace.get_tracer(_TRACER_NAME)


# Only these attribute keys may reach a span — an allow-list, so a future
# caller can't accidentally export prompt text or variant coordinates.
_ALLOWED_SPAN_ATTRS = frozenset({
    "agent.iteration", "agent.step", "agent.tool_name", "agent.tool_success",
    "agent.fallback_triggered", "agent.n_steps", "agent.error",
    "llm.backend", "llm.model_id", "llm.prompt_tokens", "llm.completion_tokens",
    "llm.latency_ms", "llm.estimated_cost_usd", "llm.stop_reason", "llm.n_tool_calls",
    "llm.price_table_version",
})


def _clean_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v for k, v in attrs.items()
        if k in _ALLOWED_SPAN_ATTRS and v is not None and isinstance(v, (str, bool, int, float))
    }


class _SpanHandle:
    """Thin wrapper so callers can add attributes whether or not OTel is live."""

    def __init__(self, span: Any = None) -> None:
        self._span = span

    def set_attributes(self, attrs: dict[str, Any]) -> None:
        if self._span is None:
            return
        for k, v in _clean_attrs(attrs).items():
            self._span.set_attribute(k, v)


@contextlib.contextmanager
def span(name: str, attrs: Optional[dict[str, Any]] = None) -> Iterator[_SpanHandle]:
    """Context manager: an OTel span when enabled, otherwise a no-op handle."""
    tracer = _get_tracer()
    if tracer is None:
        yield _SpanHandle(None)
        return
    with tracer.start_as_current_span(name) as otel_span:
        handle = _SpanHandle(otel_span)
        if attrs:
            handle.set_attributes(attrs)
        yield handle


def call_span_attrs(record: LLMCallRecord) -> dict[str, Any]:
    return {
        "agent.iteration": record.iteration,
        "llm.backend": record.backend,
        "llm.model_id": record.model_id,
        "llm.prompt_tokens": record.prompt_tokens,
        "llm.completion_tokens": record.completion_tokens,
        "llm.latency_ms": round(record.latency_ms, 2),
        "llm.estimated_cost_usd": record.estimated_cost_usd,
        "llm.stop_reason": record.stop_reason,
        "llm.n_tool_calls": record.n_tool_calls,
        "llm.price_table_version": PRICE_TABLE_VERSION,
        "agent.error": record.error,
    }
