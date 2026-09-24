"""When Ollama is down, the Lambda's audit record must say the report came
from the offline template, not "rag" — render_with_rag() used to swallow the
failure and return render_offline() output, so the handler never saw None."""
import sys
import types
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "ai-report") not in sys.path:
    sys.path.insert(0, str(ROOT / "ai-report"))

METRICS = {"sample": "HG002_chr20", "validation_pass": True,
           "validation": {"snp": {"precision": 0.99, "recall": 0.99, "f1": 0.99}},
           "provenance": {"git_commit": "abc1234", "truth_version": "GIAB-v4.2.1"}}


@pytest.fixture
def ollama_down(monkeypatch):
    fake_rag = types.ModuleType("rag")

    class _Embed:
        def embed(self, text):
            return [0.0]

    class _Retriever:
        @classmethod
        def from_directory(cls, d):
            return cls()

        def retrieve(self, *a, **k):
            return []

    fake_rag.EmbeddingModel = _Embed
    fake_rag.FAISSRetriever = _Retriever
    monkeypatch.setitem(sys.modules, "rag", fake_rag)

    def _refuse(*a, **k):
        raise requests.ConnectionError("ollama not running")

    monkeypatch.setattr(requests, "post", _refuse)


def test_render_with_rag_can_report_failure_instead_of_falling_back(ollama_down):
    import infer

    assert infer.render_with_rag(METRICS, "unused", fallback=False) is None
    # CLI default is unchanged: it still falls back to the offline renderer.
    assert "AI-DRAFTED" in infer.render_with_rag(METRICS, "unused")


def test_lambda_rag_attempt_returns_none_when_ollama_is_down(ollama_down):
    from lambdas.report_generator.handler import _try_rag_generation

    assert _try_rag_generation(METRICS) is None
