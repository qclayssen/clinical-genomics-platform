#!/usr/bin/env python3
"""Draft a plain-language report from a sample's metrics.json.

Four modes, in order of preference:
  --rag            retrieval-augmented generation via local vector store + Ollama
  --adapter PATH   use a fine-tuned QLoRA adapter over the base model
  (default)        zero-shot fallback prompt against a local/base instruct model
  --offline        deterministic template renderer — no model, no GPU, no network
                   (used in CI and for a guaranteed demo)

Whatever the mode, the output is passed through enforce_guardrails() so the review
banner and provenance line can never be dropped.
"""
import argparse
import json
import logging
import os
import re
import sys

logger = logging.getLogger(__name__)

BANNER = "AI-DRAFTED — REQUIRES CLINICIAN REVIEW"

# Default path to the FAISS index directory (relative to this script)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INDEX_DIR = os.path.join(_SCRIPT_DIR, "rag", "index")


def load_metrics(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


def _build_rag_query(m: dict) -> str:
    """Extract gene/variant identifiers from metrics to build an embedding query."""
    parts: list[str] = []
    prov = m.get("provenance", {})
    sample = m.get("sample", "unknown")
    caller = prov.get("caller", "unknown")
    n_variants = prov.get("n_variants")

    parts.append(f"Sample {sample} variant calling with {caller}")
    if n_variants is not None:
        parts.append(f"{n_variants} variants called")

    # Include validation metrics for context
    snp = m.get("validation", {}).get("snp", {})
    if snp:
        parts.append(f"SNP F1={snp.get('f1', 'n/a')}")

    return " ".join(parts)


def _enforce_word_count(text: str, min_words: int = 120, max_words: int = 300) -> str:
    """Enforce word count bounds [min_words, max_words] on report body.

    - If < min_words: append filler requesting clinician review
    - If > max_words: truncate at sentence boundary closest to max_words
    """
    words = text.split()
    word_count = len(words)

    if word_count < min_words:
        filler = (
            " This report is provided as an AI-generated draft summary. "
            "A qualified clinician should review all variant calls, quality metrics, "
            "and validation results before any clinical decisions are made. "
            "The automated analysis pipeline provides metrics for informational purposes only. "
            "Further manual review of the underlying data is strongly recommended."
        )
        text = text.rstrip() + filler

    elif word_count > max_words:
        # Truncate at sentence boundary closest to max_words
        truncated = " ".join(words[:max_words])
        # Find the last sentence-ending punctuation
        last_period = truncated.rfind(".")
        last_excl = truncated.rfind("!")
        last_q = truncated.rfind("?")
        last_boundary = max(last_period, last_excl, last_q)

        if last_boundary > 0:
            text = truncated[: last_boundary + 1]
        else:
            # No sentence boundary found; hard-truncate at word limit
            text = truncated + "."

    return text


def render_with_rag(
    m: dict,
    index_dir: str,
    ollama_model: str = "phi3:mini",
) -> str:
    """Generate a report using RAG: embed query, retrieve context, call Ollama LLM.

    Falls back to render_offline() on any Ollama failure (timeout, OOM, missing model).
    """
    import requests
    from rag import EmbeddingModel, FAISSRetriever

    # 1. Build query from metrics
    query_text = _build_rag_query(m)
    logger.info("RAG query: %s", query_text)

    # 2. Embed query using sentence-transformers
    embedder = EmbeddingModel()
    query_embedding = embedder.embed(query_text)

    # 3. Retrieve top-5 passages (cosine similarity >= 0.70) from FAISS index
    retriever = FAISSRetriever.from_directory(index_dir)
    passages = retriever.retrieve(query_embedding, top_k=5, threshold=0.70)
    logger.info("Retrieved %d passages from vector store", len(passages))

    # 4. Construct prompt: system instructions + retrieved passages + structured metrics
    system_instructions = (
        "You are a clinical genomics report writer. Generate a concise summary "
        "of the variant calling results. Do NOT make clinical recommendations, "
        "diagnoses, or treatment suggestions. The report must be between 120 and "
        "300 words."
    )

    context_section = ""
    if passages:
        context_lines = []
        for i, p in enumerate(passages, 1):
            context_lines.append(f"[Context {i}] {p['text']}")
        context_section = "\n\nRelevant context:\n" + "\n".join(context_lines)

    metrics_section = f"\n\nStructured metrics:\n{json.dumps(m, indent=2)}"

    prompt = (
        f"{system_instructions}"
        f"{context_section}"
        f"{metrics_section}"
        f"\n\nWrite a concise clinical genomics report summary (120-300 words):"
    )

    # 5. Call Ollama API with 120-second timeout
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": ollama_model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()
        report_body = result.get("response", "").strip()
    except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
        logger.warning("Ollama request failed (%s); falling back to offline renderer", exc)
        return render_offline(m)
    except Exception as exc:
        logger.warning("Ollama unexpected error (%s); falling back to offline renderer", exc)
        return render_offline(m)

    if not report_body:
        logger.warning("Ollama returned empty response; falling back to offline renderer")
        return render_offline(m)

    # 6. Enforce word count bounds [120, 300]
    report_body = _enforce_word_count(report_body)

    return report_body


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
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--base-model", default="meta-llama/Llama-3.2-3B-Instruct")
    ap.add_argument("--offline", action="store_true",
                    help="deterministic renderer, no model required")
    ap.add_argument("--rag", action="store_true",
                    help="use RAG-augmented generation via local vector store + Ollama")
    ap.add_argument("--ollama-model", default="phi3:mini",
                    help="Ollama model name for RAG generation (default: phi3:mini)")
    ap.add_argument("--index-dir", default=DEFAULT_INDEX_DIR,
                    help="path to FAISS index directory (default: ai-report/rag/index)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    m = load_metrics(args.metrics)
    if args.offline:
        report = render_offline(m)
    elif args.rag:
        try:
            report = render_with_rag(m, args.index_dir, args.ollama_model)
        except Exception as exc:  # noqa: BLE001 — degrade gracefully to offline
            logger.warning("RAG path unavailable (%s); using offline renderer", exc)
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
