#!/usr/bin/env python3
"""Extract structured fields from free-text ED/ICU consultation notes.

This demonstrates the "LLM APIs to extract structured codified data from
unstructured ED/ICU consultation notes" workflow (the VVED research stream)
using this repo's existing multi-provider LLM backend abstraction
(`ai-report/agent/llm.py`) — imported, not forked.

Two modes:
  --offline (default)  deterministic, dependency-free, keyword-based extraction.
                        No API key, no network. Guaranteed runnable for CI/demo.
  --backend NAME        real LLM backend (ollama/openai/anthropic/azure_foundry/
                        bedrock) via agent.llm.create_backend(). Falls back to
                        the offline extractor on any backend error, exactly like
                        ai-report/infer.py falls back to render_offline().

Every result — offline or model-backed — passes through
enforce_extraction_guardrails(): a mandatory "AI-EXTRACTED — REQUIRES CLINICIAN
VALIDATION" banner, a provenance line (backend, model, extraction timestamp,
sha256 of the source note), and a scrub of any advice-shaped phrasing. This
mirrors ai-report/infer.py's enforce_guardrails() (ADR-0008); the model only
ever sees the free-text note, never any other patient field.

Usage:
    python emr-pipeline/llm/structure_consult_notes.py --offline
    python emr-pipeline/llm/structure_consult_notes.py --backend openai
    python emr-pipeline/llm/structure_consult_notes.py --offline --out results.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_MODULE_DIR = _HERE.parent
_AI_REPORT_DIR = _MODULE_DIR.parent / "ai-report"
if str(_AI_REPORT_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_REPORT_DIR))

DEFAULT_SOURCE_DB = _MODULE_DIR / "mock_emr" / "mock_emr.db"
PROMPT_TEMPLATE_PATH = _HERE / "prompt_template.md"

BANNER = "AI-EXTRACTED — REQUIRES CLINICIAN VALIDATION"

VALID_DISPOSITIONS = {"admit_icu", "admit_hdu", "admit_ward", "discharge", "refer", "unknown"}
VALID_ACUITY = {"critical", "high", "moderate", "low", "unknown"}

# Small, explicitly-not-authoritative keyword -> ICD-10-AM-style code map for
# the offline fallback. Real coding is a clinical coder's job; this is a demo
# of the field-mapping pattern, not a coding engine.
_DIAGNOSIS_KEYWORDS = [
    ("urosepsis", "A41.9"), ("sepsis", "A41.9"), ("septic shock", "A41.9"),
    ("copd", "J44.1"), ("pneumonia", "J18.9"),
    ("dka", "E10.1"), ("diabetic ketoacidosis", "E10.1"), ("ketoacidosis", "E10.1"),
    ("cardiac arrest", "I46.9"), ("rosc", "I46.9"),
    ("mva", "T07"), ("polytrauma", "T07"), ("trauma", "T07"),
    ("haematemesis", "K92.2"), ("gi bleed", "K92.2"),
    ("asthma", "J46"),
    ("aaa", "Z98.8"), ("cabg", "Z98.8"), ("post-op", "Z98.8"), ("post op", "Z98.8"),
    ("pancreatitis", "K85.9"),
    ("respiratory failure", "J96.0"),
    ("tbi", "S06.9"), ("brain injury", "S06.9"), ("fall from height", "S06.9"),
    ("necrotising fasciitis", "M72.6"),
]


@dataclass
class StructuredConsultNote:
    """Validated output schema — mirrors the strictness of the variant agent's
    tool-call schemas in ai-report/agent/tools.py (explicit allowed values,
    no free-form fields beyond the note-derived text)."""

    consult_id: str
    presenting_complaint: str
    disposition: str
    acuity_flag: str
    diagnosis_code_guess: str
    banner: str = BANNER
    requires_clinician_validation: bool = True
    provenance: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.disposition not in VALID_DISPOSITIONS:
            self.disposition = "unknown"
        if self.acuity_flag not in VALID_ACUITY:
            self.acuity_flag = "unknown"
        # Guardrails are load-bearing: never let a backend response silently
        # disable the review flag or drop the banner.
        self.banner = BANNER
        self.requires_clinician_validation = True

    def to_dict(self) -> dict:
        return asdict(self)


def _note_sha256(note: str) -> str:
    return hashlib.sha256(note.encode("utf-8")).hexdigest()


def _extract_offline(note: str) -> dict:
    """Deterministic keyword/regex extraction. No model, no network."""
    text = note.lower()

    # presenting_complaint: everything up to the first period, trimmed.
    first_sentence = note.split(".")[0].strip()
    complaint = first_sentence[:80] if first_sentence else "unknown"

    admit_seen = bool(re.search(r"\badmi(t|ssion)", text))
    if re.search(r"\bicu\b", text) and (admit_seen or "retrieval to icu" in text):
        disposition = "admit_icu"
    elif re.search(r"\bhdu\b", text) and admit_seen:
        disposition = "admit_hdu"
    elif "ward" in text and admit_seen:
        disposition = "admit_ward"
    elif "discharge" in text:
        disposition = "discharge"
    elif "refer" in text:
        disposition = "refer"
    else:
        disposition = "unknown"

    if "critical" in text:
        acuity = "critical"
    elif "high acuity" in text:
        acuity = "high"
    elif "moderate" in text:
        acuity = "moderate"
    elif "low acuity" in text:
        acuity = "low"
    elif "severe" in text:
        acuity = "high"
    else:
        acuity = "unknown"

    diagnosis_code = "unknown"
    for keyword, code in _DIAGNOSIS_KEYWORDS:
        if keyword in text:
            diagnosis_code = code
            break

    return {
        "presenting_complaint": complaint,
        "disposition": disposition,
        "acuity_flag": acuity,
        "diagnosis_code_guess": diagnosis_code,
    }


def _extract_with_backend(note: str, backend_name: str) -> tuple[dict, str, str]:
    """Call a real LLM backend via agent.llm.create_backend(). Returns
    (fields, backend_name_used, model_id_used). Falls back to the offline
    extractor on any error — never crashes the pipeline on a flaky provider."""
    from agent.llm import Message, create_backend  # local import: only needed here

    backend = create_backend(backend_name)
    if not backend.is_available():
        return _extract_offline(note), "offline-rule-based (backend unavailable)", "n/a"

    prompt = PROMPT_TEMPLATE_PATH.read_text().split("---", 1)[1].replace("{CONSULT_NOTE}", note)
    try:
        response = backend.generate([Message(role="user", content=prompt)], temperature=0.0)
        parsed = json.loads(response.content.strip())
        fields = {
            "presenting_complaint": str(parsed.get("presenting_complaint", "unknown"))[:80],
            "disposition": str(parsed.get("disposition", "unknown")),
            "acuity_flag": str(parsed.get("acuity_flag", "unknown")),
            "diagnosis_code_guess": str(parsed.get("diagnosis_code_guess", "unknown")),
        }
        return fields, backend.name, backend.model_id
    except Exception:
        # Backend/network/parse failure: degrade to the offline path rather
        # than failing the run, mirroring infer.py's render_with_model fallback.
        return _extract_offline(note), f"offline-rule-based (fallback from {backend_name})", "n/a"


_ADVICE_PATTERN = re.compile(r"(?i)\b(we recommend|diagnos\w+ with|treat\w+ with|prescribe)\b")


def enforce_extraction_guardrails(
    fields: dict, consult_id: str, note: str, backend_name: str, model_id: str,
) -> StructuredConsultNote:
    """Guarantee the banner, provenance, and advice scrub survive whatever the
    (rule-based or model) extractor produced. Mirrors ai-report/infer.py's
    enforce_guardrails() (ADR-0008)."""
    cleaned = {
        k: (_ADVICE_PATTERN.sub("[review required]", v) if isinstance(v, str) else v)
        for k, v in fields.items()
    }
    result = StructuredConsultNote(
        consult_id=consult_id,
        presenting_complaint=cleaned.get("presenting_complaint", "unknown"),
        disposition=cleaned.get("disposition", "unknown"),
        acuity_flag=cleaned.get("acuity_flag", "unknown"),
        diagnosis_code_guess=cleaned.get("diagnosis_code_guess", "unknown"),
    )
    result.provenance = {
        "backend": backend_name,
        "model_id": model_id,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "source_note_sha256": _note_sha256(note),
    }
    return result


def structure_note(consult_id: str, note: str, offline: bool, backend_name: str) -> StructuredConsultNote:
    if offline:
        fields = _extract_offline(note)
        backend_used, model_used = "offline-rule-based", "n/a"
    else:
        fields, backend_used, model_used = _extract_with_backend(note, backend_name)
    return enforce_extraction_guardrails(fields, consult_id, note, backend_used, model_used)


def load_consult_notes(source_db_path: Path) -> list[tuple[str, str]]:
    conn = sqlite3.connect(source_db_path)
    try:
        rows = conn.execute("SELECT consult_id, consult_note FROM ed_consultations").fetchall()
    finally:
        conn.close()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=str(DEFAULT_SOURCE_DB), help="mock EMR sqlite path")
    ap.add_argument("--offline", action="store_true", default=True,
                     help="deterministic rule-based extraction (default; no API key needed)")
    ap.add_argument("--backend", default=None,
                     help="real LLM backend name (ollama/openai/anthropic/azure_foundry/bedrock); "
                          "implies non-offline mode")
    ap.add_argument("--out", default=None, help="write JSON results here instead of stdout")
    args = ap.parse_args()

    offline = args.backend is None
    source_db_path = Path(args.source)
    if not source_db_path.exists():
        print(f"mock EMR not found at {source_db_path} — run "
              f"emr-pipeline/mock_emr/build_mock_emr.py first", file=sys.stderr)
        return 1

    notes = load_consult_notes(source_db_path)
    results = [
        structure_note(consult_id, note, offline=offline, backend_name=args.backend or "deterministic").to_dict()
        for consult_id, note in notes
    ]

    output = json.dumps(results, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(output)
        print(f"wrote {len(results)} structured notes to {args.out}", file=sys.stderr)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
