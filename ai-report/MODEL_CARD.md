# Model Card — CGP Report Drafter

A model card is a short, standardised description of an ML model: what it's for, how it was
built, and — most importantly — what it must **not** be used for. Publishing one is standard
practice for responsible ML.

## Overview

| Field | Value |
|---|---|
| **Name** | CGP Report Drafter |
| **Purpose** | Draft a plain-language summary from a validated genomics `metrics.json` |
| **Type** | Instruction-tuned causal LLM, adapted with LoRA/QLoRA |
| **Framework** | PyTorch (`transformers` + `peft` + `trl`) |
| **Base model** | Llama-3.2-3B-Instruct or Phi-3-mini (small open-weight) |
| **Adaptation** | QLoRA — 4-bit quantized base + LoRA adapters (`peft`) |
| **Smoke-test model** | `sshleifer/tiny-gpt2` (CPU, for pipeline testing only — not for output) |
| **Intended users** | Bioinformatics/lab staff, as a *drafting aid* only |

## Intended use

- **In scope:** producing a first-draft, human-reviewed summary of already-computed QC and
  validation metrics, in plain language, with citations back to the source fields.
- **Out of scope (must not be used for):**
  - Any clinical decision, diagnosis, or treatment recommendation.
  - Interpreting the significance of individual variants.
  - Generating a final report without human review.

## How it was built

1. **Data.** Structured→summary pairs. A seed set is generated deterministically
   (`make_dataset.py`) and a hand-curated sample ships in
   `data/report_pairs.sample.jsonl` (includes pass and fail cases, both callers, and
   edge cases like low depth / high duplication).
2. **Training.** QLoRA supervised fine-tuning (`train_lora.py`) — 4-bit base model, LoRA
   adapters on the attention projections, single GPU, a few hours. A CPU **smoke test**
   (`train_smoke.py`) runs the identical loop on a tiny model in ~1 minute for CI.
3. **Serving.** `infer.py` loads the base model + adapter and generates; if the model path
   is unavailable it degrades to a zero-shot prompt, then to a deterministic offline
   renderer — so a report is always produced.

## Guardrails (enforced in code, see ADR-0008)

Every output is passed through `enforce_guardrails()`, which **cannot be bypassed**:

- The banner **"AI-DRAFTED — REQUIRES CLINICIAN REVIEW"** is guaranteed present.
- The provenance line is guaranteed present.
- Advice-like phrasing (`recommend`, `diagnose`, `treat with…`) is scrubbed.
- The model only ever sees the structured metrics — never raw reads or the VCF body.

These behaviours are covered by unit tests in `tests/test_build_metrics.py`.

## Evaluation

Because the task is templated and guardrail-bound, evaluation focuses on **faithfulness and
compliance**, not open-ended fluency:

- **Field faithfulness** — every number in the summary must match the source JSON (no
  invented values). Checkable programmatically.
- **Guardrail compliance** — banner + provenance present, no advice phrasing. Unit-tested.
- **Pass/fail correctness** — the summary's stated verdict matches `validation_pass`.

> Note: a small model fine-tuned on a modest synthetic set produces *coherent, correctly
> structured* drafts, not authoritative clinical prose. That is acceptable **by design** —
> the human reviewer is the decision-maker (ADR-0008).

## Limitations & risks

- **Hallucination** is possible; mitigated (not eliminated) by guardrails + mandatory review.
- Trained/validated only on the GIAB chr20 germline SNV shape of data (ADR-0001); other
  assays would need new data and re-validation.
- The keyword scrub is a coarse backstop, not semantic safety.

## Ethical & responsible-use notes

This is a **drafting aid inside a human-in-the-loop workflow**, deliberately built to *reduce*
the chance of unreviewed AI text reaching a clinical context. It is a portfolio artifact, not
a certified medical device.
