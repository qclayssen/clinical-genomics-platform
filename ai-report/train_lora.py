#!/usr/bin/env python3
"""QLoRA fine-tune a small open model to draft clinical-style summaries.

Deliberately small and single-GPU friendly (Colab/RunPod). Uses 4-bit quantization
+ LoRA adapters via peft/trl so the whole thing fits in ~10-12 GB VRAM.

  python train_lora.py --data data/synth_report_pairs.jsonl --out checkpoints/cgp-lora
  python train_lora.py ... --mlflow   # + local MLflow tracking/registry (pip install mlflow)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tracking  # noqa: E402  (stdlib-only; mlflow is imported lazily and optional)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--base-model", default="meta-llama/Llama-3.2-3B-Instruct")
    ap.add_argument("--out", default="checkpoints/cgp-lora")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-4)
    tracking.add_cli_args(ap)
    args = ap.parse_args()

    # Imports kept inside main so --help works without a GPU stack installed.
    import torch
    from datasets import load_dataset
    from peft import LoraConfig, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
    )
    from trl import SFTConfig, SFTTrainer

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

    lora_params = dict(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                       target_modules=["q_proj", "k_proj", "v_proj", "o_proj"])
    peft_config = LoraConfig(task_type="CAUSAL_LM", **lora_params)

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
    tracker = tracking.start_tracking(
        args.mlflow, base_model=args.base_model, data_path=args.data,
        script="ai-report/train_lora.py", experiment=args.mlflow_experiment,
        run_name=args.mlflow_run_name, registered_model=args.mlflow_model_name,
    )
    with tracker:
        tracker.log_params({
            "base_model": args.base_model, "epochs": args.epochs,
            "learning_rate": args.lr, "per_device_train_batch_size": args.batch_size,
            "gradient_accumulation_steps": args.grad_accum, "max_seq_length": 1024,
            "quantization": "4bit-nf4-double-quant", "compute_dtype": "bfloat16",
            "n_train_examples": len(dataset),
            **{f"lora_{k}": (",".join(v) if isinstance(v, list) else v)
               for k, v in lora_params.items()},
        })
        trainer.train()
        trainer.save_model(args.out)
        print(f"saved LoRA adapter to {args.out}")
        tracker.log_history(trainer.state.log_history)
        tracker.log_adapter(args.out)
        if tracker.enabled:
            print(f"mlflow run id: {tracker.run_id}")


if __name__ == "__main__":
    main()
