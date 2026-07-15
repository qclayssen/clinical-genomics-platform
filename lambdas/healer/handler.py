"""AI-Powered Healer Lambda handler.

Diagnoses ambiguous pipeline failures using Ollama LLM and recommends
actions from a fixed action set. Falls back to rule-based classification
when Ollama is unavailable or returns invalid responses.

Fixed action set:
  - retry_stricter: Retry with stricter QC parameters
  - retry_more_memory: Retry with increased memory allocation
  - retry_longer_timeout: Retry with extended timeout
  - quarantine_soft: Apply soft quarantine to the sample
  - quarantine_hard: Apply hard quarantine to the sample
  - escalate_to_human: Escalate to operator for manual review

Requirements: Task 10 — AI diagnostics with rule-based fallback.
"""

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ─── Fixed Action Set ─────────────────────────────────────────────────────────
VALID_ACTIONS = frozenset({
    "retry_stricter",
    "retry_more_memory",
    "retry_longer_timeout",
    "quarantine_soft",
    "quarantine_hard",
    "escalate_to_human",
})

# ─── Diagnostic Prompt Template ───────────────────────────────────────────────
DIAGNOSTIC_PROMPT = """You are a clinical genomics pipeline failure diagnostician.

Analyze the following pipeline failure and recommend ONE action from this fixed set:
- retry_stricter: QC parameters too lenient, retry with stricter filtering
- retry_more_memory: Process ran out of memory, retry with more resources
- retry_longer_timeout: Process timed out, retry with longer duration
- quarantine_soft: Sample quality issue, apply soft quarantine for review
- quarantine_hard: Repeated/severe quality issue, apply hard quarantine
- escalate_to_human: Cannot determine cause, needs operator investigation

Failure context:
- Run ID: {run_id}
- Sample ID: {sample_id}
- Error cause: {error_cause}
- Failed state: {failed_state}
- Attempt number: {attempt_number}

Respond ONLY with a JSON object:
{{"action": "<one of the valid actions>", "reasoning": "<brief explanation>", "confidence": <0.0-1.0>}}
"""

# ─── Rule-Based Classification (Fallback) ─────────────────────────────────────

# Patterns for rule-based classification
OOM_PATTERNS = ["137", "outofmemory", "oom", "killed", "memory", "cannot allocate"]
TIMEOUT_PATTERNS = ["timeout", "timed out", "timeouterror", "states.timeout", "deadline"]
QC_PATTERNS = ["qc", "threshold", "quality", "duplication", "f1", "precision", "recall",
               "exit code 42", "qc_soft_fail"]
HARD_FAIL_PATTERNS = ["exit code 43", "qc_hard_fail", "corruption", "invalid format"]


def rule_based_classify(error_cause: str, attempt_number: int = 1) -> dict:
    """Classify failure using deterministic rules when LLM is unavailable.

    Args:
        error_cause: String describing the error.
        attempt_number: Current attempt number (affects escalation).

    Returns:
        Dict with action, reasoning, confidence.
    """
    cause_lower = error_cause.lower()

    # Check for OOM/memory issues
    if any(p in cause_lower for p in OOM_PATTERNS):
        return {
            "action": "retry_more_memory",
            "reasoning": "Error pattern matches memory exhaustion (OOM/signal 137)",
            "confidence": 0.85,
        }

    # Check for timeout
    if any(p in cause_lower for p in TIMEOUT_PATTERNS):
        return {
            "action": "retry_longer_timeout",
            "reasoning": "Error pattern matches timeout/deadline exceeded",
            "confidence": 0.85,
        }

    # Check for hard QC failure
    if any(p in cause_lower for p in HARD_FAIL_PATTERNS):
        return {
            "action": "quarantine_hard",
            "reasoning": "Error pattern matches non-retryable quality failure",
            "confidence": 0.80,
        }

    # Check for QC threshold breach
    if any(p in cause_lower for p in QC_PATTERNS):
        if attempt_number >= 2:
            return {
                "action": "quarantine_soft",
                "reasoning": "QC failure persists after retry — quarantine for review",
                "confidence": 0.75,
            }
        return {
            "action": "retry_stricter",
            "reasoning": "QC threshold breach — retry with stricter parameters",
            "confidence": 0.80,
        }

    # Default: escalate to human
    return {
        "action": "escalate_to_human",
        "reasoning": "Error cause does not match known patterns — requires operator review",
        "confidence": 0.60,
    }


# ─── Ollama Integration ───────────────────────────────────────────────────────

def _call_ollama(prompt: str, timeout_seconds: int = 30) -> str | None:
    """Call Ollama API for LLM inference.

    Args:
        prompt: The diagnostic prompt.
        timeout_seconds: Request timeout.

    Returns:
        LLM response text, or None on failure.
    """
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")

    try:
        import urllib.request
        import urllib.error

        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 200},
        }).encode()

        req = urllib.request.Request(
            f"{ollama_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            result = json.loads(resp.read().decode())
            return result.get("response", "")

    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        logger.warning(f"Ollama unavailable: {e}")
        return None
    except Exception as e:
        logger.warning(f"Ollama unexpected error: {e}")
        return None


def _parse_llm_response(response: str) -> dict | None:
    """Parse LLM response and validate it contains a valid action.

    Args:
        response: Raw LLM response text.

    Returns:
        Parsed dict with action/reasoning/confidence, or None if invalid.
    """
    if not response:
        return None

    # Try to extract JSON from the response
    try:
        # LLM might wrap JSON in markdown code blocks
        clean = response.strip()
        if "```" in clean:
            # Extract content between code fences
            parts = clean.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    clean = part
                    break

        # Find the JSON object in the response
        start = clean.find("{")
        end = clean.rfind("}") + 1
        if start == -1 or end == 0:
            return None

        parsed = json.loads(clean[start:end])

        # Validate action is in fixed set
        action = parsed.get("action", "")
        if action not in VALID_ACTIONS:
            return None

        # Validate confidence is a float in [0, 1]
        confidence = parsed.get("confidence", 0.5)
        if not isinstance(confidence, (int, float)):
            confidence = 0.5
        confidence = max(0.0, min(1.0, float(confidence)))

        return {
            "action": action,
            "reasoning": str(parsed.get("reasoning", "LLM recommendation")),
            "confidence": confidence,
        }

    except (json.JSONDecodeError, KeyError, TypeError):
        return None


# ─── Lambda Handler ───────────────────────────────────────────────────────────

def handler(event: dict, context: Any = None) -> dict:
    """Lambda entry point for the AI-powered healer.

    Diagnoses pipeline failures and recommends remediation actions.
    Uses Ollama LLM when available, falls back to rule-based classification.

    Args:
        event: Step Functions payload containing:
            - run_id: Unique run identifier
            - sample_id: Sample identifier
            - error: Error details from the failed state
                - Cause: Error cause string
            - failed_state: Name of the state that failed (optional)
            - attempt_number: Self-healing attempt number (optional)
        context: Lambda context (unused).

    Returns:
        Dict with:
            - action: One of the fixed action set
            - reasoning: Explanation of the recommendation
            - confidence: Float 0.0-1.0 indicating certainty
            - source: "llm" or "rule_based"
            - run_id: Echo back for state machine routing
            - sample_id: Echo back for state machine routing
    """
    run_id = event.get("run_id", "unknown")
    sample_id = event.get("sample_id", "unknown")
    error = event.get("error", {})
    error_cause = error.get("Cause", "") if isinstance(error, dict) else str(error)
    failed_state = event.get("failed_state", "unknown")
    attempt_number = int(event.get("attempt_number", 1))

    logger.info(json.dumps({
        "action": "healer_invoked",
        "run_id": run_id,
        "sample_id": sample_id,
        "error_cause": error_cause[:200],
        "failed_state": failed_state,
        "attempt_number": attempt_number,
    }))

    # Try LLM diagnosis first
    recommendation = None
    source = "rule_based"

    prompt = DIAGNOSTIC_PROMPT.format(
        run_id=run_id,
        sample_id=sample_id,
        error_cause=error_cause[:500],
        failed_state=failed_state,
        attempt_number=attempt_number,
    )

    llm_response = _call_ollama(prompt)
    if llm_response:
        recommendation = _parse_llm_response(llm_response)
        if recommendation:
            source = "llm"
            logger.info(json.dumps({
                "action": "llm_recommendation",
                "run_id": run_id,
                "recommended_action": recommendation["action"],
                "confidence": recommendation["confidence"],
            }))

    # Fall back to rule-based if LLM unavailable or invalid response
    if recommendation is None:
        recommendation = rule_based_classify(error_cause, attempt_number)
        source = "rule_based"
        logger.info(json.dumps({
            "action": "rule_based_fallback",
            "run_id": run_id,
            "recommended_action": recommendation["action"],
            "reason": "ollama_unavailable" if llm_response is None else "invalid_llm_response",
        }))

    return {
        "action": recommendation["action"],
        "reasoning": recommendation["reasoning"],
        "confidence": recommendation["confidence"],
        "source": source,
        "run_id": run_id,
        "sample_id": sample_id,
    }
