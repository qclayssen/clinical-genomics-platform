"""Tests for LLM observability on the variant-interpretation agent (AI-8).

Covers token / latency / cost accounting end to end with the deterministic
backend and mocked backends — no network, no real LLM, no OpenTelemetry
install required. Key honesty properties under test:

- unreported token counts stay ``None`` (never zero-filled);
- cost is ``None`` whenever it can't be estimated (unknown model, missing usage);
- nothing recorded carries prompt text or variant coordinates.
"""

import json
import re
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_AI_REPORT_DIR = _ROOT / "ai-report"
if str(_AI_REPORT_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_REPORT_DIR))

from agent import observability as obs  # noqa: E402
from agent import react  # noqa: E402
from agent.llm import (  # noqa: E402
    BedrockBackend,
    DeterministicBackend,
    LLMBackend,
    LLMResponse,
    _parse_openai_style_response,
)
from agent.react import ReActAgent, Variant  # noqa: E402
from agent.trace import AgentTrace, RunTrace  # noqa: E402

VARIANT = Variant(chrom="chr20", pos=4699605, ref="G", alt="A", gene="PRNP", genotype="heterozygous")


# ═══ Mock backends ════════════════════════════════════════════════════════════


class _UsageOverrideBackend(LLMBackend):
    """Drives the real deterministic tool-calling script but reports a chosen
    model id and token usage, as a paid backend would."""

    def __init__(self, model_id: str, usage: dict, name: str = "mock") -> None:
        self._inner = DeterministicBackend()
        self._model_id = model_id
        self._usage = usage
        self._name = name
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_id(self) -> str:
        return self._model_id

    def generate(self, messages, tools=None, temperature=0.1, max_tokens=1024) -> LLMResponse:
        self.calls += 1
        resp = self._inner.generate(messages, tools, temperature, max_tokens)
        resp.usage = dict(self._usage)
        resp.model = self._model_id
        return resp


class _FailingBackend(LLMBackend):
    @property
    def name(self) -> str:
        return "broken"

    @property
    def model_id(self) -> str:
        return "broken/model"

    def generate(self, messages, tools=None, temperature=0.1, max_tokens=1024) -> LLMResponse:
        raise ConnectionError("backend down")


class _TickClock:
    """perf_counter stand-in advancing a fixed step per call → deterministic latency."""

    def __init__(self, step_s: float = 0.01) -> None:
        self._t = 0.0
        self._step = step_s

    def perf_counter(self) -> float:
        self._t += self._step
        return self._t


@pytest.fixture
def tick_clock(monkeypatch):
    import time as real_time

    clock = _TickClock(0.01)  # every measured interval = 10 ms
    monkeypatch.setattr(react, "time", types.SimpleNamespace(perf_counter=clock.perf_counter, time=real_time.time))
    return clock


def _run(backend) -> react.InterpretationResult:
    agent = ReActAgent(backend=backend)
    try:
        return agent.run(VARIANT)
    finally:
        agent.close()


# ═══ Cost estimation ══════════════════════════════════════════════════════════


def test_price_table_is_dated_and_versioned():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", obs.PRICE_TABLE_AS_OF)
    assert obs.PRICE_TABLE_AS_OF in obs.PRICE_TABLE_VERSION


def test_estimate_cost_for_known_model():
    # gpt-4o-mini: 0.15 in / 0.60 out per 1M tokens
    cost = obs.estimate_cost_usd("openai/gpt-4o-mini", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.75)
    assert obs.estimate_cost_usd("openai/gpt-4o-mini", 1000, 500) == pytest.approx(0.00045)


def test_estimate_cost_unknown_model_is_none_not_zero():
    assert obs.estimate_cost_usd("azure_foundry/my-deployment", 1000, 500) is None


@pytest.mark.parametrize("prompt,completion", [(None, 10), (10, None), (None, None)])
def test_estimate_cost_with_missing_usage_is_none(prompt, completion):
    assert obs.estimate_cost_usd("openai/gpt-4o-mini", prompt, completion) is None


@pytest.mark.parametrize("model_id", ["deterministic-v1", "ollama/llama3.2:3b"])
def test_local_backends_have_zero_cost_even_without_usage(model_id):
    assert obs.estimate_cost_usd(model_id, None, None) == 0.0


# ═══ Per-call records and aggregation ═════════════════════════════════════════


def test_record_from_response_keeps_unreported_usage_as_none():
    resp = LLMResponse(usage={"input_tokens": None, "output_tokens": None}, stop_reason="tool_use")
    rec = obs.record_from_response(iteration=0, backend="openai", model_id="openai/gpt-4o-mini",
                                   response=resp, latency_ms=12.5)
    assert rec.prompt_tokens is None and rec.completion_tokens is None
    assert rec.total_tokens is None
    assert rec.estimated_cost_usd is None


def test_record_from_response_with_empty_usage_dict():
    rec = obs.record_from_response(iteration=0, backend="x", model_id="x/y",
                                   response=LLMResponse(usage={}), latency_ms=1.0)
    assert rec.prompt_tokens is None


def test_summarize_calls_separates_unreported_usage_and_nulls_partial_cost():
    calls = [
        obs.LLMCallRecord(0, "openai", "openai/gpt-4o-mini", 100, 20, 10.0,
                          obs.estimate_cost_usd("openai/gpt-4o-mini", 100, 20)),
        obs.LLMCallRecord(1, "openai", "openai/gpt-4o-mini", None, None, 30.0, None),
    ]
    s = obs.summarize_calls(calls)
    assert s["n_llm_calls"] == 2
    assert s["n_calls_without_usage"] == 1
    assert s["prompt_tokens"] == 100 and s["completion_tokens"] == 20
    assert s["total_latency_ms"] == 40.0
    assert s["mean_latency_ms"] == 20.0
    assert s["max_latency_ms"] == 30.0
    assert s["estimated_cost_usd"] is None  # partial sum would understate cost


def test_summarize_empty_calls():
    s = obs.summarize_calls([])
    assert s["n_llm_calls"] == 0
    assert s["prompt_tokens"] == 0
    assert s["estimated_cost_usd"] == 0
    assert s["mean_latency_ms"] is None


# ═══ ReAct loop accounting ════════════════════════════════════════════════════


def test_deterministic_backend_records_one_call_per_iteration(tick_clock):
    result = _run(DeterministicBackend())
    assert not result.fallback_triggered
    calls = result.llm_calls
    assert len(calls) >= 2
    assert [c.iteration for c in calls] == list(range(len(calls)))
    assert all(c.backend == "deterministic" and c.model_id == "deterministic-v1" for c in calls)
    # The deterministic backend truthfully reports zero tokens and costs nothing.
    assert all(c.prompt_tokens == 0 and c.completion_tokens == 0 for c in calls)
    assert all(c.estimated_cost_usd == 0.0 for c in calls)
    assert all(c.latency_ms == pytest.approx(10.0) for c in calls)
    # Each record points at a real step of the existing trace.
    assert all(c.trace_step_index is not None and 0 <= c.trace_step_index < len(result.trace) for c in calls)
    assert result.llm_usage["total_latency_ms"] == pytest.approx(10.0 * len(calls))


def test_paid_backend_tokens_latency_and_cost(tick_clock):
    backend = _UsageOverrideBackend("openai/gpt-4o-mini", {"input_tokens": 200, "output_tokens": 50}, name="openai")
    result = _run(backend)
    n = backend.calls
    assert len(result.llm_calls) == n
    usage = result.llm_usage
    assert usage["prompt_tokens"] == 200 * n
    assert usage["completion_tokens"] == 50 * n
    assert usage["n_calls_without_usage"] == 0
    assert usage["estimated_cost_usd"] == pytest.approx(n * (200 * 0.15 + 50 * 0.60) / 1_000_000)
    assert usage["total_latency_ms"] == pytest.approx(10.0 * n)
    # Existing total_tokens field agrees with the per-call accounting.
    assert result.total_tokens == 250 * n


def test_backend_without_usage_is_not_zero_filled(tick_clock):
    backend = _UsageOverrideBackend("azure_foundry/dep", {"input_tokens": None, "output_tokens": None},
                                    name="azure_foundry")
    result = _run(backend)
    assert result.llm_calls
    assert all(c.prompt_tokens is None and c.completion_tokens is None for c in result.llm_calls)
    usage = result.llm_usage
    assert usage["n_calls_without_usage"] == len(result.llm_calls)
    assert usage["estimated_cost_usd"] is None
    assert result.total_tokens == 0  # budget can only count what was reported


def test_failed_llm_call_is_recorded_with_latency_and_unknown_usage(tick_clock):
    result = _run(_FailingBackend())
    assert result.fallback_triggered
    assert len(result.llm_calls) == 1
    call = result.llm_calls[0]
    assert call.error is True
    assert call.stop_reason == "error"
    assert call.prompt_tokens is None and call.estimated_cost_usd is None
    assert call.latency_ms == pytest.approx(10.0)
    assert result.llm_usage["n_failed_calls"] == 1


# ═══ Existing trace carries the accounting ════════════════════════════════════


def test_agent_trace_and_run_trace_include_llm_usage():
    backend = _UsageOverrideBackend("openai/gpt-4o-mini", {"input_tokens": 10, "output_tokens": 5})
    result = _run(backend)
    at = AgentTrace.from_result(result, run_id="run_x")
    d = at.to_dict()
    assert d["llm_usage"]["n_llm_calls"] == backend.calls
    assert len(d["llm_calls"]) == backend.calls
    rt = RunTrace(run_id="run_x", variant_traces=[at, at]).to_dict()
    assert rt["summary"]["llm_usage"]["prompt_tokens"] == 2 * 10 * backend.calls
    json.dumps(rt)  # serialisable


def test_llm_call_records_hold_no_text_or_coordinates():
    result = _run(DeterministicBackend())
    blob = json.dumps([c.to_dict() for c in result.llm_calls])
    for forbidden in ("4699605", "PRNP", "chr20", "Please interpret"):
        assert forbidden not in blob
    allowed = {"iteration", "backend", "model_id", "prompt_tokens", "completion_tokens", "latency_ms",
               "estimated_cost_usd", "stop_reason", "n_tool_calls", "trace_step_index", "error", "total_tokens"}
    assert set(result.llm_calls[0].to_dict()) == allowed


# ═══ Persisted aggregate row ══════════════════════════════════════════════════


def test_call_metrics_row_matches_table_columns_and_has_no_phi():
    from api.repository import AGENT_CALL_METRICS_COLUMNS

    result = _run(_UsageOverrideBackend("openai/gpt-4o-mini", {"input_tokens": 10, "output_tokens": 5}))
    row = obs.build_call_metrics_row(run_id="run_x", backend_used=result.backend_used,
                                     fallback_triggered=result.fallback_triggered,
                                     wall_time_ms=result.wall_time_ms, calls=result.llm_calls)
    assert set(row) == set(AGENT_CALL_METRICS_COLUMNS)
    assert row["usage_complete"] is True
    assert row["price_table_version"] == obs.PRICE_TABLE_VERSION
    assert "4699605" not in json.dumps(row)


def test_call_metrics_row_tokens_null_when_nothing_reported():
    calls = [obs.LLMCallRecord(0, "azure_foundry", "azure_foundry/d", None, None, 5.0, None)]
    row = obs.build_call_metrics_row(run_id="r", backend_used="azure_foundry/d", fallback_triggered=False,
                                     wall_time_ms=6.0, calls=calls)
    assert row["prompt_tokens"] is None and row["completion_tokens"] is None
    assert row["usage_complete"] is False
    assert row["estimated_cost_usd"] is None


def test_call_metrics_row_for_deterministic_path_without_llm_calls():
    row = obs.build_call_metrics_row(run_id="r", backend_used="deterministic-fallback",
                                     fallback_triggered=True, wall_time_ms=3.0, calls=[])
    assert row["n_llm_calls"] == 0
    assert row["prompt_tokens"] == 0  # truly zero: no LLM was called
    assert row["backend"] == "deterministic-fallback"
    assert row["estimated_cost_usd"] == 0


# ═══ Backends never fabricate usage ═══════════════════════════════════════════


def test_openai_style_response_without_usage_reports_none():
    msg = MagicMock(content="hi", tool_calls=None)
    resp = MagicMock(choices=[MagicMock(message=msg, finish_reason="stop")], usage=None)
    parsed = _parse_openai_style_response(resp, "openai/gpt-4o-mini")
    assert parsed.usage == {"input_tokens": None, "output_tokens": None}


def test_bedrock_response_without_usage_reports_none():
    backend = BedrockBackend(model_id="anthropic.claude-3-5-haiku-20241022-v1:0", region="us-east-1")
    client = MagicMock()
    client.converse.return_value = {
        "output": {"message": {"role": "assistant", "content": [{"text": "hi"}]}},
        "stopReason": "end_turn",
    }
    backend._client = client
    from agent.llm import Message

    parsed = backend.generate([Message(role="user", content="hi")])
    assert parsed.usage == {"input_tokens": None, "output_tokens": None}


# ═══ Optional OpenTelemetry export ════════════════════════════════════════════


def test_otel_disabled_by_default_is_noop(monkeypatch):
    monkeypatch.delenv("AGENT_OTEL_ENABLED", raising=False)
    assert obs.otel_enabled() is False
    with obs.span("agent.run", {"llm.backend": "x"}) as h:
        h.set_attributes({"llm.prompt_tokens": 1})  # no error, nothing exported


def test_otel_enabled_but_not_installed_is_noop(monkeypatch):
    monkeypatch.setenv("AGENT_OTEL_ENABLED", "1")
    monkeypatch.setitem(sys.modules, "opentelemetry", None)  # forces ImportError
    result = _run(DeterministicBackend())
    assert result.llm_calls  # agent unaffected


class _FakeSpan:
    def __init__(self, name, sink):
        self.name, self.attrs = name, {}
        sink.append(self)

    def set_attribute(self, k, v):
        self.attrs[k] = v

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_otel_spans_per_step_with_allowlisted_attributes_only(monkeypatch):
    spans: list[_FakeSpan] = []
    tracer = types.SimpleNamespace(start_as_current_span=lambda name: _FakeSpan(name, spans))
    otel_trace = types.SimpleNamespace(get_tracer=lambda _name: tracer)
    fake_pkg = types.ModuleType("opentelemetry")
    fake_pkg.trace = otel_trace
    monkeypatch.setitem(sys.modules, "opentelemetry", fake_pkg)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", otel_trace)
    monkeypatch.setenv("AGENT_OTEL_ENABLED", "true")

    backend = _UsageOverrideBackend("openai/gpt-4o-mini", {"input_tokens": 7, "output_tokens": 3}, name="openai")
    result = _run(backend)

    names = [s.name for s in spans]
    assert names.count("agent.run") == 1
    assert names.count("agent.llm_call") == backend.calls == len(result.llm_calls)
    assert names.count("agent.tool_call") >= 1
    llm_span = next(s for s in spans if s.name == "agent.llm_call")
    assert llm_span.attrs["llm.prompt_tokens"] == 7
    assert llm_span.attrs["llm.model_id"] == "openai/gpt-4o-mini"
    assert "llm.estimated_cost_usd" in llm_span.attrs
    for s in spans:
        assert set(s.attrs) <= obs._ALLOWED_SPAN_ATTRS
        assert "4699605" not in json.dumps(s.attrs, default=str)


def test_span_attribute_allowlist_drops_unknown_keys():
    assert obs._clean_attrs({"prompt": "secret", "llm.backend": "x", "llm.prompt_tokens": None}) == {
        "llm.backend": "x"
    }


# ═══ Schema / migration consistency ═══════════════════════════════════════════


def _create_table_block(sql: str) -> str:
    m = re.search(r"CREATE TABLE IF NOT EXISTS agent_call_metrics \(.*?\n\);", sql, re.S)
    assert m, "agent_call_metrics table definition not found"
    return m.group(0)


def test_migration_0002_table_matches_schema_sql():
    schema = (_ROOT / "db" / "schema.sql").read_text()
    migration = (_ROOT / "db" / "migrations" / "0002_agent_call_metrics.sql").read_text()
    assert _create_table_block(schema) == _create_table_block(migration)


def test_agent_call_metrics_is_insert_only_in_schema_and_migration():
    schema = (_ROOT / "db" / "schema.sql").read_text()
    assert "'agent_call_metrics'" in schema
    migration = (_ROOT / "db" / "migrations" / "0002_agent_call_metrics.sql").read_text()
    assert "BEFORE UPDATE OR DELETE ON agent_call_metrics" in migration
    assert "BEFORE TRUNCATE ON agent_call_metrics" in migration


def test_repository_columns_exist_in_table():
    from api.repository import AGENT_CALL_METRICS_COLUMNS

    block = _create_table_block((_ROOT / "db" / "schema.sql").read_text())
    for col in AGENT_CALL_METRICS_COLUMNS:
        assert re.search(rf"^\s+{col}\s", block, re.M), col
