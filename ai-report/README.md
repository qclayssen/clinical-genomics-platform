# AI-assisted reporting

Turns a sample's structured `metrics.json` into a **plain-language draft summary**.

## ML stack (PyTorch)

This is genuine ML fine-tuning, built on the **PyTorch** ecosystem:

| Library | Role |
|---|---|
| **PyTorch** | Tensor/autograd backend everything runs on |
| **transformers** | Model loading, tokenizer, `Trainer` |
| **peft** | LoRA adapters (parameter-efficient fine-tuning) |
| **trl** | Supervised fine-tuning loop (`SFTTrainer`) |
| **bitsandbytes** | 4-bit quantization for QLoRA (GPU) |

See the **[Model Card](MODEL_CARD.md)** for intended use, guardrails, evaluation, and
limitations, and **[ADR-0007](../docs/adr/0007-qlora-small-open-model.md)** for *why* QLoRA
on a small open model was chosen.

## Three execution paths (graceful degradation)

1. **Fine-tuned** (`train_lora.py` → `infer.py --adapter`) — QLoRA-tune a small open model
   (Llama-3.2-3B-Instruct or Phi-3-mini) on structured-output → summary pairs. Needs a GPU.
2. **Fallback prompt** (`prompts/fallback_prompt.md`) — a documented zero-shot prompt for
   any instruct model, used when no fine-tuned checkpoint is available.
3. **Offline renderer** (`infer.py --offline`) — deterministic, **no ML dependencies at
   all**; guarantees a compliant report even with no model/GPU/network.

## CPU smoke test (runs anywhere, no GPU)

`train_smoke.py` runs the **identical fine-tuning loop** (data → LoRA → train → save →
generate) on a tiny model in ~1 minute, so the training path is runnable and CI-testable
without a GPU:

```bash
pip install torch transformers datasets peft     # CPU wheels are fine
python train_smoke.py                            # uses data/report_pairs.sample.jsonl
```

Verified output shows the LoRA adapter training and a saved checkpoint; the tiny model's
generated text is intentionally gibberish — the point is that the *loop* works.

## Non-negotiable guardrails

Every generated report:
- carries a fixed **"AI-DRAFTED — REQUIRES CLINICIAN REVIEW"** banner it cannot omit;
- cites the **structured fields** it drew each statement from (no free invention);
- is written from the `metrics.json` only — the model never sees raw reads or the VCF body.

This is the pattern regulated-industry LLM deployments use: the model drafts, a human signs.

## Usage

```bash
pip install -r requirements.txt

# Build synthetic training pairs (bootstrap, then hand-edit for quality)
python make_dataset.py --n 120 --out data/synth_report_pairs.jsonl
# (a curated 12-example sample already ships in data/report_pairs.sample.jsonl)

# Fine-tune for real (single GPU, a few hours on Colab/RunPod)
python train_lora.py --data data/synth_report_pairs.jsonl --out checkpoints/cgp-lora

# ...or just prove the loop works on CPU in ~1 minute
python train_smoke.py

# Draft a report from a real pipeline output
python infer.py --metrics ../results/HG002_chr20/export/HG002_chr20.metrics.json \
                --adapter checkpoints/cgp-lora   # omit --adapter for the fallback prompt
python infer.py --metrics <metrics.json> --offline   # no ML deps at all
```
