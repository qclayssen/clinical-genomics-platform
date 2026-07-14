#!/usr/bin/env python3
"""Draft a plain-language report from a sample's metrics.json.

Three modes, in order of preference:
  --adapter PATH   use a fine-tuned QLoRA adapter over the base model
  (default)        zero-shot fallback prompt against a local/base instruct model
  --offline        deterministic template renderer — no model, no GPU, no network
                   (used in CI and for a guaranteed demo)

Whatever the mode, the output is passed through enforce_guardrails() so the review
banner and provenance line can never be dropped.
"""
import argparse
import json
import re
import sys

BANNER = "AI-DRAFTED — REQUIRES CLINICIAN REVIEW"


def load_metrics(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


def render_offline(m: dict) -> str:
    """Deterministic, dependency-free renderer. Always guardrail-compliant."""
    snp = m.get("validation", {}).get("snp", {})
    prov = m.get("provenance", {})
    p = snp.get("precision")
    r = snp.get("recall")
    f1 = snp.get("f1")
    dup = m.get("qc", {}).get("percent_duplication")
    passed = m.get("validation_pass")
    nvar = prov.get("n_variants")

    def pct(x):
        return f"{x*100:.1f}%" if isinstance(x, (int, float)) else "n/a"

    verdict = (
        "The run met the F1 ≥ 0.99 acceptance threshold."
        if passed else
        "The run did NOT meet the acceptance threshold; results should not be used "
        "until reviewed by a clinician."
    )
    lines = [
        BANNER,
        "",
        f"Sample {m.get('sample','?')} was processed with the "
        f"{prov.get('caller','?')} variant caller. {verdict}",
        f"SNV precision {pct(p)} (validation.snp.precision), "
        f"recall {pct(r)} (validation.snp.recall), "
        f"F1 {pct(f1)} (validation.snp.f1).",
    ]
    if nvar is not None:
        lines.append(f"{nvar:,} variants were called (provenance.n_variants).")
    if dup is not None:
        lines.append(f"Duplication rate {pct(dup)} (qc.percent_duplication) as a "
                     "library-quality indicator.")
    lines.append("No clinical interpretation of individual variants is provided.")
    lines.append("")
    lines.append(f"Provenance: git {prov.get('git_commit','?')}, "
                 f"{prov.get('truth_version','?')}.")
    return "\n".join(lines)


def render_with_model(m: dict, adapter: str | None, base_model: str) -> str:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch

    tok = AutoTokenizer.from_pretrained(base_model)
    model = AutoModelForCausalLM.from_pretrained(base_model, device_map="auto",
                                                 torch_dtype=torch.bfloat16)
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter)

    prompt_tmpl = open(__file__.rsplit("/", 1)[0] + "/prompts/fallback_prompt.md").read()
    user = prompt_tmpl.split("---", 1)[1].replace("{METRICS_JSON}", json.dumps(m, indent=2))
    messages = [{"role": "user", "content": user}]
    inputs = tok.apply_chat_template(messages, return_tensors="pt",
                                     add_generation_prompt=True).to(model.device)
    out = model.generate(inputs, max_new_tokens=400, do_sample=False)
    return tok.decode(out[0][inputs.shape[1]:], skip_special_tokens=True).strip()


def enforce_guardrails(text: str, m: dict) -> str:
    """The model output is untrusted: guarantee the banner + provenance survive."""
    if BANNER not in text:
        text = BANNER + "\n\n" + text
    prov = m.get("provenance", {})
    if "Provenance:" not in text:
        text += (f"\n\nProvenance: git {prov.get('git_commit','?')}, "
                 f"{prov.get('truth_version','?')}.")
    # Strip any hallucinated clinical-recommendation phrasing as a belt-and-braces check
    text = re.sub(r"(?i)\b(we recommend|diagnos\w+|treat\w+ with)\b",
                  "[review required]", text)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--base-model", default="meta-llama/Llama-3.2-3B-Instruct")
    ap.add_argument("--offline", action="store_true",
                    help="deterministic renderer, no model required")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    m = load_metrics(args.metrics)
    if args.offline:
        report = render_offline(m)
    else:
        try:
            report = render_with_model(m, args.adapter, args.base_model)
        except Exception as exc:  # noqa: BLE001 — degrade gracefully to offline
            print(f"[warn] model path unavailable ({exc}); using offline renderer",
                  file=sys.stderr)
            report = render_offline(m)

    report = enforce_guardrails(report, m)

    if args.out:
        with open(args.out, "w") as fh:
            fh.write(report + "\n")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
