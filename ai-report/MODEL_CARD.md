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
3. **Tracking & registry (opt-in).** Run either trainer with `--mlflow` (needs
   `pip install mlflow`) to record the run in a local MLflow store — see
   [Experiment tracking & provenance](#experiment-tracking--provenance) below.
4. **Serving.** `infer.py` loads the base model + adapter and generates; if the model path
   is unavailable it degrades to a zero-shot prompt, then to a deterministic offline
   renderer — so a report is always produced.

## Experiment tracking & provenance

Training is tracked with **MLflow** when the `--mlflow` flag is passed
([ADR-0035](../docs/adr/0035-mlflow-local-tracking-model-registry.md); shared logic in
`tracking.py`). It is opt-in: without the flag, or without `mlflow` installed, the trainers run
exactly as before (the latter with a warning).

```bash
pip install mlflow
python ai-report/train_smoke.py --mlflow                       # CPU, ~1 min
python ai-report/train_lora.py --data data/synth_report_pairs.jsonl --mlflow   # GPU
mlflow ui --backend-store-uri sqlite:///ai-report/mlruns/mlflow.db   # http://127.0.0.1:5000
```

The store is local only (SQLite + artifacts under `ai-report/mlruns/`, gitignored; set
`MLFLOW_TRACKING_URI` to use another). Each tracked run records:

| Kind | What |
|---|---|
| Params | learning rate, epochs/steps, batch/accumulation, sequence length, quantization, LoRA r/alpha/dropout/target modules |
| Metrics | loss curve (`loss` per logged step), `grad_norm`, `learning_rate`, final `train_loss` |
| Tags | `git_commit` (`-dirty` if uncommitted changes), `dataset_sha256`, `base_model`, `version.torch/transformers/peft/datasets/trl/mlflow`, `adapter_sha256` |
| Artifact | the saved LoRA adapter directory (`adapter/`) |

The adapter is then **registered** as a new version of `cgp-report-drafter-adapter` in the local
model registry. **That registered version (`cgp-report-drafter-adapter/<n>`) is the provenance
reference for the adapter**: it links to the run, and through its tags to the exact code,
data, base model and library stack. An adapter trained without `--mlflow` has no such record.

Known gaps: the registered version is not yet written into `infer.py`'s output, so a draft does
not itself name the adapter version that produced it; and the MLflow store is mutable (runs and
versions can be deleted) — it is a traceability aid, not covered by the insert-only guarantees
of the results stores.

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
