# ADR-0008 — Enforce AI guardrails and human-in-the-loop in code

**Status:** Accepted · **Date:** 2026-05-24

## Context

An LLM can hallucinate, drop required disclaimers, or drift into giving medical advice. In a
clinical-style context that is unacceptable. Relying on the model to *choose* to behave, or
on a prompt instruction it might ignore, is not a control. The safety behaviour must hold
even if the model output is wrong.

## Decision

Treat model output as **untrusted** and pass it through a deterministic
`enforce_guardrails()` step that **cannot be skipped**:

- Guarantee the banner **"AI-DRAFTED — REQUIRES CLINICIAN REVIEW"** is present (re-inserted
  if missing).
- Guarantee the provenance line is present.
- Scrub advice-like phrasing (`we recommend`, `diagnose`, `treat with…`) to a
  `[review required]` marker.
- Require field-level citations in the drafted text; the model never sees raw reads or the
  VCF body, only the structured metrics.

A qualified human reviews and signs off every report (**human-in-the-loop**); the banner
stays until they do. These rules are covered by unit tests (`tests/test_build_metrics.py`).

## Consequences

**Good**
- Safety does not depend on model behaviour — it's enforced in plain, tested code.
- Mirrors how regulated industries actually deploy LLMs: the model drafts, a human decides.
- Makes the AI feature *defensible in an interview*: "what stops it giving bad advice?" has a
  concrete, testable answer.

**Bad / accepted limitations**
- The scrub is a coarse safety net (keyword-based), not semantic understanding; it is a
  backstop on top of prompt design, not a substitute for human review.
- Enforcing a fixed banner/format slightly constrains the model's phrasing freedom — an
  acceptable trade for guaranteed compliance.

## Alternatives considered

- **Trust the system prompt to enforce the rules** — rejected: a prompt is a request, not a
  guarantee; the model can ignore it.
- **A second LLM as a judge/filter** — more flexible but adds cost, latency, and *another*
  fallible model; the deterministic check is simpler and always runs.
- **No human sign-off** — unacceptable in any clinical-adjacent framing.
