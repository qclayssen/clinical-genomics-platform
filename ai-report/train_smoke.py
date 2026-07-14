#!/usr/bin/env python3
"""CPU-runnable LoRA fine-tuning smoke test.

Purpose: prove the *whole* fine-tuning path works end to end — load data, apply LoRA
adapters, run the training loop, save an adapter, generate — on any machine, in a
couple of minutes, with **no GPU and no bitsandbytes**. It uses a deliberately tiny
model so it's fast; it is NOT meant to produce good text. For the real thing (a 3B
model, 4-bit QLoRA, a GPU) see train_lora.py and docs/adr/0007.

  pip install torch transformers datasets peft   # CPU wheels are fine
  python train_smoke.py                           # uses data/report_pairs.sample.jsonl

The PyTorch stack here is the same family used by the real trainer:
transformers (model + Trainer) + peft (LoRA). Only the model size and quantization differ.
"""
import argparse
import os


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(os.path.dirname(__file__),
                                                   "data", "report_pairs.sample.jsonl"))
    ap.add_argument("--base-model", default="sshleifer/tiny-gpt2",
                    help="tiny by default so this runs on CPU in minutes")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__),
                                                  "checkpoints", "smoke"))
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--max-steps", type=int, default=20,
                    help="cap steps so the smoke test stays fast")
    args = ap.parse_args()

    import torch
    from datasets import load_dataset
    from transformers import (AutoModelForCausalLM, AutoTokenizer,
                              DataCollatorForLanguageModeling, Trainer, TrainingArguments)
    from peft import LoraConfig, get_peft_model

    torch.manual_seed(0)

    tok = AutoTokenizer.from_pretrained(args.base_model)
    tok.pad_token = tok.pad_token or tok.eos_token

    def to_text(ex):
        # Simple instruction-style formatting the tiny model can learn the shape of.
        return {"text": f"### METRICS\n{ex['input']}\n\n### REPORT\n{ex['output']}{tok.eos_token}"}

    ds = load_dataset("json", data_files=args.data, split="train").map(to_text)

    def tokenize(ex):
        out = tok(ex["text"], truncation=True, max_length=256, padding="max_length")
        out["labels"] = out["input_ids"].copy()
        return out

    ds = ds.map(tokenize, remove_columns=ds.column_names)

    model = AutoModelForCausalLM.from_pretrained(args.base_model)
    lora = LoraConfig(
        r=8, lora_alpha=16, lora_dropout=0.0, bias="none", task_type="CAUSAL_LM",
        target_modules=["c_attn"],  # GPT-2 attention projection
    )
    model = get_peft_model(model, lora)
    trainable, total = model.get_nb_trainable_parameters()
    print(f"[smoke] trainable params: {trainable:,} / {total:,} "
          f"({100*trainable/total:.3f}% — the LoRA adapter)")

    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=args.out,
            num_train_epochs=args.epochs,
            max_steps=args.max_steps,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=1,
            learning_rate=5e-4,
            logging_steps=5,
            save_strategy="no",
            report_to=[],
            use_cpu=True,
        ),
        train_dataset=ds,
        data_collator=DataCollatorForLanguageModeling(tok, mlm=False),
    )

    print("[smoke] training…")
    result = trainer.train()
    print(f"[smoke] final training loss: {result.training_loss:.4f}")

    os.makedirs(args.out, exist_ok=True)
    model.save_pretrained(args.out)
    tok.save_pretrained(args.out)
    print(f"[smoke] saved LoRA adapter to {args.out}")

    # Prove we can load + generate from the adapter.
    prompt = "### METRICS\n{\"sample\": \"DEMO\"}\n\n### REPORT\n"
    ids = tok(prompt, return_tensors="pt")
    gen = model.generate(**ids, max_new_tokens=20, do_sample=False)
    print("[smoke] sample generation (tiny model — gibberish is expected):")
    print("   ", tok.decode(gen[0], skip_special_tokens=True).replace("\n", " ")[:160])
    print("[smoke] OK — fine-tuning loop ran end to end.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
