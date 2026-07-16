"""Tests for AI-Powered Healer Lambda.

Validates:
- Mocked Ollama: correct action parsed from LLM response
- Fallback on timeout: rule-based produces valid action
- Malformed LLM response → defaults to escalate_to_human (via rule-based)
- Actions always from fixed set
- Rule-based classification for known patterns
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from lambdas.healer.handler import (
    VALID_ACTIONS,
    _parse_llm_response,
    handler,
    rule_based_classify,
)

# ══════════════════════════════════════════════════════════════════════════════
# Test: Rule-based classification
# ══════════════════════════════════════════════════════════════════════════════


class TestRuleBasedClassify:
    """Test deterministic rule-based classification."""

    def test_oom_signal_137(self):
        """Exit code 137 → retry_more_memory."""
        result = rule_based_classify("Process terminated with exit code 137")
        assert result["action"] == "retry_more_memory"
        assert result["confidence"] > 0

    def test_oom_explicit(self):
        """Explicit OOM message → retry_more_memory."""
        result = rule_based_classify("java.lang.OutOfMemoryError: Java heap space")
        assert result["action"] == "retry_more_memory"

    def test_timeout_error(self):
        """Timeout → retry_longer_timeout."""
        result = rule_based_classify("States.Timeout: Task timed out after 900 seconds")
        assert result["action"] == "retry_longer_timeout"

    def test_timed_out_message(self):
        """'timed out' message → retry_longer_timeout."""
        result = rule_based_classify("Lambda function timed out")
        assert result["action"] == "retry_longer_timeout"

    def test_qc_threshold_breach_first_attempt(self):
        """QC breach on first attempt → retry_stricter."""
        result = rule_based_classify("QC threshold breach: duplication >20%", attempt_number=1)
        assert result["action"] == "retry_stricter"

    def test_qc_threshold_breach_second_attempt(self):
        """QC breach on second attempt → quarantine_soft."""
        result = rule_based_classify("QC threshold breach: F1 below 0.99", attempt_number=2)
        assert result["action"] == "quarantine_soft"

    def test_exit_code_42(self):
        """Exit code 42 → retry_stricter (QC soft fail)."""
        result = rule_based_classify("Process failed with exit code 42")
        assert result["action"] == "retry_stricter"

    def test_exit_code_43(self):
        """Exit code 43 → quarantine_hard (QC hard fail)."""
        result = rule_based_classify("Process failed with exit code 43")
        assert result["action"] == "quarantine_hard"

    def test_unknown_error(self):
        """Unknown error → escalate_to_human."""
        result = rule_based_classify("Something completely unexpected happened XYZ123")
        assert result["action"] == "escalate_to_human"

    def test_all_results_in_valid_actions(self):
        """All rule-based results are from the fixed action set."""
        test_cases = [
            "signal 137 killed",
            "timed out after 900s",
            "QC threshold breach",
            "exit code 43",
            "unknown weird error",
            "",
        ]
        for cause in test_cases:
            result = rule_based_classify(cause)
            assert result["action"] in VALID_ACTIONS, (
                f"Action '{result['action']}' not in VALID_ACTIONS for cause: {cause}"
            )

    def test_confidence_is_float(self):
        """Confidence is always a float."""
        result = rule_based_classify("any error")
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0


# ══════════════════════════════════════════════════════════════════════════════
# Test: LLM response parsing
# ══════════════════════════════════════════════════════════════════════════════


class TestParseLlmResponse:
    """Test LLM response parsing and validation."""

    def test_valid_json_response(self):
        """Valid JSON with correct action → parsed successfully."""
        response = '{"action": "retry_stricter", "reasoning": "QC issue", "confidence": 0.9}'
        result = _parse_llm_response(response)
        assert result is not None
        assert result["action"] == "retry_stricter"
        assert result["confidence"] == 0.9

    def test_json_in_code_block(self):
        """JSON wrapped in markdown code block → parsed."""
        response = '```json\n{"action": "retry_more_memory", "reasoning": "OOM", "confidence": 0.85}\n```'
        result = _parse_llm_response(response)
        assert result is not None
        assert result["action"] == "retry_more_memory"

    def test_invalid_action(self):
        """Invalid action not in fixed set → None."""
        response = '{"action": "reboot_server", "reasoning": "try rebooting", "confidence": 0.9}'
        result = _parse_llm_response(response)
        assert result is None

    def test_malformed_json(self):
        """Malformed JSON → None."""
        result = _parse_llm_response("This is not JSON at all")
        assert result is None

    def test_empty_response(self):
        """Empty response → None."""
        result = _parse_llm_response("")
        assert result is None

    def test_none_response(self):
        """None response → None."""
        result = _parse_llm_response(None)
        assert result is None

    def test_confidence_clamped(self):
        """Confidence > 1.0 is clamped to 1.0."""
        response = '{"action": "escalate_to_human", "reasoning": "sure", "confidence": 1.5}'
        result = _parse_llm_response(response)
        assert result["confidence"] == 1.0

    def test_confidence_clamped_below_zero(self):
        """Negative confidence is clamped to 0.0."""
        response = '{"action": "escalate_to_human", "reasoning": "unsure", "confidence": -0.5}'
        result = _parse_llm_response(response)
        assert result["confidence"] == 0.0

    def test_json_with_surrounding_text(self):
        """JSON with surrounding text → extracts and parses."""
        response = 'Here is my analysis:\n{"action": "quarantine_soft", "reasoning": "repeated failure", "confidence": 0.75}\nDone.'
        result = _parse_llm_response(response)
        assert result is not None
        assert result["action"] == "quarantine_soft"


# ══════════════════════════════════════════════════════════════════════════════
# Test: Handler with mocked Ollama
# ══════════════════════════════════════════════════════════════════════════════


class TestHandlerWithMockedOllama:
    """Test handler with mocked Ollama responses."""

    @patch("lambdas.healer.handler._call_ollama")
    def test_handler_with_valid_llm_response(self, mock_ollama):
        """Handler uses LLM recommendation when valid."""
        mock_ollama.return_value = '{"action": "retry_stricter", "reasoning": "QC breach detected", "confidence": 0.92}'

        event = {
            "run_id": "run-001",
            "sample_id": "HG002",
            "error": {"Cause": "QC threshold breach: F1 below 0.995"},
            "failed_state": "ValidateResults",
            "attempt_number": 1,
        }
        result = handler(event)

        assert result["action"] == "retry_stricter"
        assert result["source"] == "llm"
        assert result["confidence"] == 0.92
        assert result["run_id"] == "run-001"
        assert result["sample_id"] == "HG002"

    @patch("lambdas.healer.handler._call_ollama")
    def test_handler_falls_back_on_ollama_unavailable(self, mock_ollama):
        """Handler falls back to rule-based when Ollama is unavailable."""
        mock_ollama.return_value = None

        event = {
            "run_id": "run-002",
            "sample_id": "HG002",
            "error": {"Cause": "Process terminated with signal 137"},
            "attempt_number": 1,
        }
        result = handler(event)

        assert result["action"] == "retry_more_memory"
        assert result["source"] == "rule_based"
        assert result["run_id"] == "run-002"

    @patch("lambdas.healer.handler._call_ollama")
    def test_handler_falls_back_on_invalid_llm_response(self, mock_ollama):
        """Handler falls back to rule-based when LLM gives invalid response."""
        mock_ollama.return_value = "I think you should restart everything and hope for the best"

        event = {
            "run_id": "run-003",
            "sample_id": "HG002",
            "error": {"Cause": "timed out after 900 seconds"},
            "attempt_number": 1,
        }
        result = handler(event)

        assert result["action"] == "retry_longer_timeout"
        assert result["source"] == "rule_based"

    @patch("lambdas.healer.handler._call_ollama")
    def test_handler_action_always_in_valid_set(self, mock_ollama):
        """Handler always returns an action from the fixed set."""
        # Test various LLM responses
        responses = [
            None,  # unavailable
            "",  # empty
            "garbage",  # malformed
            '{"action": "invalid_action", "reasoning": "x", "confidence": 0.9}',  # invalid action
            '{"action": "quarantine_hard", "reasoning": "severe", "confidence": 0.95}',  # valid
        ]

        for resp in responses:
            mock_ollama.return_value = resp
            event = {
                "run_id": "run-test",
                "sample_id": "HG002",
                "error": {"Cause": "some error"},
            }
            result = handler(event)
            assert result["action"] in VALID_ACTIONS, (
                f"Action '{result['action']}' not in VALID_ACTIONS for response: {resp}"
            )

    @patch("lambdas.healer.handler._call_ollama")
    def test_handler_with_missing_fields(self, mock_ollama):
        """Handler handles events with missing optional fields."""
        mock_ollama.return_value = None

        event = {"run_id": "run-minimal"}
        result = handler(event)

        assert result["action"] in VALID_ACTIONS
        assert result["run_id"] == "run-minimal"
        assert result["sample_id"] == "unknown"
