# AI-assisted reporting

Turns a sample's structured `metrics.json` into a **plain-language draft summary**.
Two paths, both documented so the platform degrades gracefully:

1. **Fine-tuned** (`train_lora.py` → `infer.py`) — QLoRA-tune a small open model
   (Llama-3.2-3B-Instruct or Phi-3-mini) on structured-output → summary pairs.
2. **Fallback** (`prompts/fallback_prompt.md`) — a documented zero-shot prompt for
   any instruct model, used when no fine-tuned checkpoint is available.

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

# Fine-tune (single GPU, a few hours on Colab/RunPod)
python train_lora.py --data data/synth_report_pairs.jsonl --out checkpoints/cgp-lora

# Draft a report from a real pipeline output
python infer.py --metrics ../results/HG002_chr20/export/HG002_chr20.metrics.json \
                --adapter checkpoints/cgp-lora        # omit --adapter to use the fallback path
```
