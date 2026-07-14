#!/usr/bin/env python3
"""QLoRA fine-tune a small open model to draft clinical-style summaries.

Deliberately small and single-GPU friendly (Colab/RunPod). Uses 4-bit quantization
+ LoRA adapters via peft/trl so the whole thing fits in ~10-12 GB VRAM.

  python train_lora.py --data data/synth_report_pairs.jsonl --out checkpoints/cgp-lora
"""
import argparse


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--base-model", default="meta-llama/Llama-3.2-3B-Instruct")
    ap.add_argument("--out", default="checkpoints/cgp-lora")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-4)
    args = ap.parse_args()

    # Imports kept inside main so --help works without a GPU stack installed.
    import torch
    from datasets import load_dataset
    from transformers import (
        AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
    )
    from peft import LoraConfig, prepare_model_for_kbit_training
    from trl import SFTTrainer, SFTConfig

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    tokenizer.pad_token = tokenizer.pad_token or tokenizer.eos_token

    SYSTEM = (
        "You are a bioinformatics reporting assistant. Draft a plain-language summary "
        "from the structured JSON. Always begin with 'AI-DRAFTED — REQUIRES CLINICIAN "
        "REVIEW', cite the source field in parentheses after each number, and never "
        "invent values or infer clinical significance."
    )

    def to_chat(example):
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Structured input:\n```json\n{example['input']}\n```"},
            {"role": "assistant", "content": example["output"]},
        ]
        return {"text": tokenizer.apply_chat_template(messages, tokenize=False)}

    dataset = load_dataset("json", data_files=args.data, split="train").map(to_chat)

    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model, quantization_config=bnb, device_map="auto"
    )
    model = prepare_model_for_kbit_training(model)

    peft_config = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        peft_config=peft_config,
        args=SFTConfig(
            output_dir=args.out,
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            learning_rate=args.lr,
            bf16=True,
            logging_steps=10,
            save_strategy="epoch",
            dataset_text_field="text",
            max_seq_length=1024,
        ),
    )
    trainer.train()
    trainer.save_model(args.out)
    print(f"saved LoRA adapter to {args.out}")


if __name__ == "__main__":
    main()
