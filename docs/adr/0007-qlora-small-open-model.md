# ADR-0007 — Fine-tune a small open model with QLoRA (PyTorch)

**Status:** Accepted · **Date:** 2026-05-21

## Context

The AI layer must turn a structured `metrics.json` into a plain-language summary. The brief
asks specifically for **fine-tuning**, not just prompting a hosted API — the point is to
demonstrate the ML engineering skill of adapting a model to a task. Constraints: a solo
budget, no data-centre, and a regulated-style context where the output must be tightly
controlled.

The whole ML stack here is **PyTorch-based**: `transformers` (model + Trainer), `peft` (LoRA
adapters), `trl` (supervised fine-tuning helper), and `bitsandbytes` (4-bit quantization) all
sit on top of PyTorch.

## Decision

**Fine-tune a small open-weight instruction model** (Llama-3.2-3B-Instruct or Phi-3-mini)
using **QLoRA** — 4-bit quantization + LoRA adapters via `peft`/`trl` — so training fits on a
single rented GPU (~10–12 GB VRAM, a few hours). Training data is generated as structured →
summary pairs (`make_dataset.py`) and hand-curated. Provide two supporting paths:

1. A **CPU smoke test** (`train_smoke.py`) that LoRA-fine-tunes a *tiny* model on the
   committed sample data in minutes, on any machine, so the training loop is runnable and
   testable without a GPU.
2. A **prompt-engineered fallback** (`prompts/fallback_prompt.md`) plus a **dependency-free
   offline renderer** so the platform still produces a compliant report when no fine-tuned
   checkpoint is available.

## Consequences

**Good**
- Demonstrates real fine-tuning (PyTorch + PEFT), not just API calls — the skill the brief
  asks for.
- QLoRA keeps cost and hardware within a solo budget; the CPU smoke test keeps the code
  *runnable and CI-testable* by anyone.
- Graceful degradation: fine-tuned → fallback prompt → offline renderer, so a demo never
  hard-fails.

**Bad / accepted limitations**
- A 3B model fine-tuned on a small synthetic set produces *coherent, well-structured* drafts,
  not clinically authoritative prose — acceptable because a human always reviews
  ([ADR-0008](0008-guardrails-human-in-the-loop.md)).
- Full GPU fine-tuning isn't run in CI (cost/hardware); CI runs the CPU smoke test instead.

## Alternatives considered

- **Hosted fine-tuning API (OpenAI / Bedrock)** — less infrastructure, but hides the ML
  engineering and creates a data-handling dependency; also weaker as a demonstrated skill.
- **Prompt engineering only, no fine-tuning** — kept as the *fallback*, but on its own it
  doesn't satisfy the "fine-tuning" ask.
- **Full fine-tuning of a large model** — unnecessary and unaffordable; QLoRA on a small
  model is the right tool for a bounded, well-defined generation task.
- **Full-precision LoRA on a mid-size model** — viable, but 4-bit QLoRA buys a big memory
  saving for negligible quality loss on this narrow task.
