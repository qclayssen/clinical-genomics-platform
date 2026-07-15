# ADR-0014 — Agentic Variant Interpretation with ReAct Loop

**Status:** Accepted · **Date:** 2026-07-15

## Context

The platform produces run-level quality metrics and a guardrailed AI summary of those
metrics (see ADR-0007, ADR-0008). The next capability gap is **individual variant
interpretation** — given a called variant, determine its clinical significance using the
ACMG/AMP 2015 framework (5-tier: Pathogenic → Benign).

This is a multi-step reasoning task: the agent must query multiple knowledge bases (ClinVar,
gnomAD, gene annotations), gather evidence codes, apply combining rules, and produce a
traceable classification. A single prompt cannot reliably do this — the LLM needs to
*use tools* iteratively based on intermediate results.

## Decision

Implement a **ReAct-style agentic loop** (Thought → Action → Observation → ... → Answer)
with a **deterministic fallback** and **multi-provider LLM support**:

1. **ReAct Agent** (`react.py`): LLM reasons about what tool to call next, dispatches tool
   calls, observes results, and iterates until it can produce a final classification.
2. **Deterministic Fallback** (`deterministic.py`): When the LLM is unavailable, loops,
   or exceeds budget — a fixed pipeline (ClinVar → gnomAD → ACMG rules → template report)
   guarantees a classification is always produced.
3. **Multi-Provider LLM** (`llm.py`): Supports Ollama (local), OpenAI, Anthropic with
   automatic fallback chain. `DeterministicBackend` for CI.
4. **Local-First Data** (`data/chr20_knowledge.db`): SQLite with ClinVar + gnomAD subsets
   for chr20 so the agent works offline and in CI without external API calls.
5. **Safety Constraints**: Enforced in code (not just prompts) — no treatment language,
   mandatory VUS uncertainty flags, review banner, evidence citations required.

## Trade-offs

| Dimension | Choice | Trade-off |
|---|---|---|
| **Latency** | ReAct loop (5+ LLM calls per variant) | Slower than single-shot, but produces traceable reasoning |
| **Reliability** | Deterministic fallback always available | Fallback classifications are more conservative (never claims Pathogenic without strong ClinVar evidence) |
| **Cost** | Local Ollama preferred, cloud optional | Local is free but lower quality; cloud costs ~$0.01/variant |
| **Safety** | Code-enforced guardrails over prompt-only | Constrains model freedom but guarantees compliance |
| **Scope** | chr20 only (matches pipeline scope) | Not a production clinical tool — demonstrates the pattern |

## Consequences

**Good**
- Demonstrates frontier AI engineering: tool-using agents under clinical safety constraints.
- Fully CI-smokable with no external dependencies (deterministic mode).
- Extends existing guardrails pattern (ADR-0008) to variant-level interpretation.
- Full observability: every tool call, thought, and observation is traced and auditable.
- Graceful degradation: cloud LLM → local Ollama → deterministic — never hard-fails.

**Bad / accepted limitations**
- The agent's classifications are limited by the local knowledge base (15 ClinVar records
  for chr20). In production, live API queries would be needed.
- ACMG classification from automated evidence alone is inherently limited — many criteria
  (PS2/de novo, PP1/segregation) require clinical data not available to the agent.
- Adding ~5 LLM calls per variant increases wall time; acceptable for a post-pipeline
  interpretation step, not suitable for real-time use.

## Alternatives considered

- **Single-prompt classification** — simpler but unreliable for multi-step reasoning;
  the LLM cannot reliably apply combining rules without intermediate verification.
- **Static rule engine only** — reliable but cannot adapt reasoning to novel variants
  or provide natural-language explanations; kept as the fallback.
- **External API-only** (ClinVar/gnomAD live) — would make CI dependent on external
  services; local SQLite subset eliminates this dependency.
- **Fine-tuned classification model** — could work but loses interpretability; the
  ReAct trace shows *why* a classification was made.
