"""Pure metric functions for the agent evaluation harness (ADR-0032).

Everything here is side-effect free and works on plain dicts (the shape of
``InterpretationResult.to_dict()``), so the metrics can be unit-tested on
hand-built traces, including deliberately hallucinating ones.

Metric definitions
------------------
* **Accuracy** — exact 5-class match (P / LP / VUS / LB / B), and a collapsed
  3-class view (P/LP, VUS, LB/B).
* **Per-class accuracy** — recall per *expected* class.
* **Opposite-direction errors** — expected P/LP called LB/B or vice versa. The
  clinically dangerous error; gated at zero.
* **Hallucinated citation** — the final summary cites a ClinVar accession that no
  ``query_clinvar`` observation in the trace returned, or asserts a ClinVar
  significance that the tool never returned (or returned differently).
* **Tool grounding** — fraction of final evidence codes whose basis appears in a
  tool observation of the same trace (see ``_code_grounded``). Codes no tool in
  the registry can produce (PS2, PS3, PP3, ...) are ungrounded by definition.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, Optional

CLASSES_5 = ["P", "LP", "VUS", "LB", "B"]
CLASSES_3 = ["P/LP", "VUS", "LB/B"]
INVALID = "INVALID"

_LABEL_MAP = {
    "pathogenic": "P",
    "p": "P",
    "likely pathogenic": "LP",
    "likely_pathogenic": "LP",
    "lp": "LP",
    "uncertain significance": "VUS",
    "uncertain_significance": "VUS",
    "vus": "VUS",
    "likely benign": "LB",
    "likely_benign": "LB",
    "lb": "LB",
    "benign": "B",
    "b": "B",
}

_COLLAPSE = {"P": "P/LP", "LP": "P/LP", "VUS": "VUS", "LB": "LB/B", "B": "LB/B"}

_SIG_WORDS = r"(likely pathogenic|pathogenic|uncertain significance|likely benign|benign|VUS)"
_CLINVAR_ID_RE = re.compile(r"\b((?:VCV|RCV|SCV)\d{6,12})(?:\.\d+)?\b")
_CLINVAR_NUMERIC_ID_RE = re.compile(
    r"ClinVar\s+(?:variation\s+)?(?:ID|accession)[\s:#]*(\d{3,12})\b", re.IGNORECASE
)
_CLINVAR_SIG_CLAIM_RE = re.compile(
    r"ClinVar\s+(?:reports|classifies|lists|records|has)\b[^.]{0,80}?\bas\s+" + _SIG_WORDS,
    re.IGNORECASE,
)


# ─── Labels ──────────────────────────────────────────────────────────────────


def normalize_class(label: Optional[str]) -> str:
    """Map any classification string to P/LP/VUS/LB/B, or ``INVALID``."""
    if not label:
        return INVALID
    return _LABEL_MAP.get(label.strip().lower().replace("-", " "), INVALID)


def collapse3(cls: str) -> str:
    """Collapse a 5-class code to P/LP, VUS, LB/B (``INVALID`` passes through)."""
    return _COLLAPSE.get(cls, INVALID)


# ─── Classification metrics ──────────────────────────────────────────────────


def accuracy(pairs: Iterable[tuple[str, str]]) -> Optional[float]:
    """Fraction of (expected, predicted) pairs that match. None if empty."""
    pairs = list(pairs)
    if not pairs:
        return None
    return sum(1 for e, p in pairs if e == p) / len(pairs)


def per_class_accuracy(
    pairs: Iterable[tuple[str, str]], labels: list[str]
) -> dict[str, dict]:
    """Per expected class: n, correct, accuracy (recall). accuracy None when n == 0."""
    out: dict[str, dict] = {}
    pairs = list(pairs)
    for lab in labels:
        n = sum(1 for e, _ in pairs if e == lab)
        c = sum(1 for e, p in pairs if e == lab and p == lab)
        out[lab] = {"n": n, "correct": c, "accuracy": (c / n) if n else None}
    return out


def confusion_matrix(
    pairs: Iterable[tuple[str, str]], labels: list[str]
) -> dict[str, dict[str, int]]:
    """Rows = expected, columns = predicted (plus an INVALID column)."""
    cols = labels + [INVALID]
    m = {e: {p: 0 for p in cols} for e in labels}
    for e, p in pairs:
        if e not in m:
            continue
        m[e][p if p in cols else INVALID] += 1
    return m


def opposite_direction_errors(pairs: Iterable[tuple[str, str]]) -> int:
    """Count P/LP <-> LB/B swaps (5-class codes in, collapsed internally)."""
    n = 0
    for e, p in pairs:
        ce, cp = collapse3(e), collapse3(p)
        if {ce, cp} == {"P/LP", "LB/B"}:
            n += 1
    return n


# ─── Trace facts ─────────────────────────────────────────────────────────────


def extract_tool_facts(trace: list[dict]) -> dict:
    """Collect what the tools actually returned in this trace.

    Handles both observation shapes in the repo: the ReAct path (full tool
    output with ``records``) and the deterministic interpreter (flattened
    ``clinical_significance`` / ``af_global`` fields).
    """
    facts = {
        "tools_called": set(),
        "clinvar_ids": set(),
        "clinvar_sigs": set(),
        "clinvar_found": False,
        "hgvs_p": set(),
        "gnomad_called": False,
        "gnomad_found": None,
        "af_global": None,
        "homozygote_count": 0,
        "gnomad_codes": set(),
        "acmg_tool_classification": None,
    }
    for step in trace or []:
        tool = step.get("tool_name") or ""
        if tool:
            facts["tools_called"].add(tool)
        if step.get("type") != "observation" and not (tool == "classify_acmg" and step.get("tool_output")):
            continue
        out = step.get("tool_output") or {}
        if tool == "query_clinvar":
            records = out.get("records")
            if records is None and out.get("clinical_significance"):
                records = [out]
            for rec in records or []:
                facts["clinvar_found"] = True
                if rec.get("variant_id"):
                    facts["clinvar_ids"].add(str(rec["variant_id"]))
                if rec.get("clinical_significance"):
                    facts["clinvar_sigs"].add(normalize_class(rec["clinical_significance"]))
                if rec.get("hgvs_p"):
                    facts["hgvs_p"].add(rec["hgvs_p"])
        elif tool == "query_gnomad":
            facts["gnomad_called"] = True
            found = out.get("found")
            facts["gnomad_found"] = bool(found) if found is not None else "af_global" in out
            if "af_global" in out:
                facts["af_global"] = float(out.get("af_global") or 0.0)
            facts["homozygote_count"] = int(out.get("homozygote_count") or 0)
            facts["gnomad_codes"].update(out.get("acmg_frequency_codes") or [])
        elif tool == "classify_acmg" and out.get("classification"):
            facts["acmg_tool_classification"] = normalize_class(out["classification"])
    return facts


def _code_grounded(code: str, facts: dict) -> bool:
    """Is this ACMG evidence code supported by something a tool returned?"""
    sigs = facts["clinvar_sigs"]
    af = facts["af_global"]
    if code in ("PS1", "PP5"):
        return bool(sigs & {"P", "LP"})
    if code == "BP6":
        return bool(sigs & {"B", "LB"})
    if code in facts["gnomad_codes"]:
        return True
    if code == "BA1":
        return af is not None and af > 0.05
    if code == "BS1":
        return af is not None and af > 0.01
    if code == "BS2":
        return af is not None and af > 0.01 and facts["homozygote_count"] > 0
    if code == "PM2":
        return facts["gnomad_called"] and (af is None or af < 0.0001)
    if code == "PVS1":
        return any(re.search(r"(Ter|\*|fs)", h) for h in facts["hgvs_p"])
    return False


def grounding(evidence_codes: list[str], facts: dict) -> dict:
    """Per-case grounding: total codes, grounded codes, and the ungrounded ones."""
    codes = list(dict.fromkeys(evidence_codes or []))
    ungrounded = [c for c in codes if not _code_grounded(c, facts)]
    return {"n_codes": len(codes), "n_grounded": len(codes) - len(ungrounded),
            "ungrounded": ungrounded}


def _accession_number(accession: str) -> int:
    """VCV000001262 -> 1262 (so 'ClinVar ID 1262' matches a returned VCV)."""
    digits = re.sub(r"\D", "", accession)
    return int(digits) if digits else -1


def find_hallucinated_citations(summary: str, facts: dict) -> list[str]:
    """Return human-readable issues for citations not backed by the trace."""
    issues: list[str] = []
    text = summary or ""
    cited = set(_CLINVAR_ID_RE.findall(text))
    cited |= {f"numeric:{n}" for n in _CLINVAR_NUMERIC_ID_RE.findall(text)}
    known = set(facts["clinvar_ids"])
    known_numeric = {_accession_number(i) for i in known}
    for cid in sorted(cited):
        if cid.startswith("numeric:"):
            if int(cid.split(":")[1]) not in known_numeric:
                issues.append(f"cited ClinVar ID {cid.split(':')[1]} not returned by any tool")
        elif cid not in known:
            issues.append(f"cited ClinVar accession {cid} not returned by any tool")
    for m in _CLINVAR_SIG_CLAIM_RE.finditer(text):
        claimed = normalize_class(m.group(1))
        if not facts["clinvar_found"]:
            issues.append(f"claims ClinVar significance '{m.group(1)}' but no ClinVar record was returned")
        elif claimed not in facts["clinvar_sigs"]:
            issues.append(f"claims ClinVar significance '{m.group(1)}' but tool returned "
                          f"{sorted(facts['clinvar_sigs'])}")
    return issues


# ─── Aggregation ─────────────────────────────────────────────────────────────


def score_case(row: dict, result: dict) -> dict:
    """Score one agent result against one gold-set row."""
    facts = extract_tool_facts(result.get("trace") or [])
    predicted = normalize_class(result.get("classification"))
    expected = row.get("expected_class")
    g = grounding(result.get("evidence_codes") or [], facts)
    halluc = find_hallucinated_citations(result.get("summary") or "", facts)
    acmg_cls = facts["acmg_tool_classification"]
    return {
        "id": row["id"],
        "tier": row["tier"],
        "expected": expected,
        "predicted": predicted,
        "correct_5": (expected == predicted) if expected else None,
        "correct_3": (collapse3(expected) == collapse3(predicted)) if expected else None,
        "evidence_codes": list(result.get("evidence_codes") or []),
        "grounding": g,
        "hallucinations": halluc,
        "queried_clinvar_and_gnomad": {"query_clinvar", "query_gnomad"} <= facts["tools_called"],
        "matches_classify_acmg": (acmg_cls == predicted) if acmg_cls else None,
        "fallback_triggered": bool(result.get("fallback_triggered")),
        "backend_used": result.get("backend_used"),
    }


def _rate(num: int, den: int) -> Optional[float]:
    return (num / den) if den else None


def aggregate(cases: list[dict], tiers: Iterable[str]) -> dict:
    """Aggregate scored cases restricted to the given tiers."""
    tiers = set(tiers)
    sel = [c for c in cases if c["tier"] in tiers]
    labelled = [c for c in sel if c["expected"]]
    pairs5 = [(c["expected"], c["predicted"]) for c in labelled]
    pairs3 = [(collapse3(e), collapse3(p)) for e, p in pairs5]
    n_codes = sum(c["grounding"]["n_codes"] for c in sel)
    n_grounded = sum(c["grounding"]["n_grounded"] for c in sel)
    n_halluc_cases = sum(1 for c in sel if c["hallucinations"])
    acmg_checked = [c for c in sel if c["matches_classify_acmg"] is not None]
    return {
        "tiers": sorted(tiers),
        "n_cases": len(sel),
        "n_labelled": len(labelled),
        "accuracy_5class": accuracy(pairs5),
        "accuracy_3class": accuracy(pairs3),
        "per_class_5": per_class_accuracy(pairs5, CLASSES_5),
        "per_class_3": per_class_accuracy(pairs3, CLASSES_3),
        "confusion_5class": confusion_matrix(pairs5, CLASSES_5),
        "confusion_3class": confusion_matrix(pairs3, CLASSES_3),
        "opposite_direction_errors": opposite_direction_errors(pairs5),
        "hallucinated_citation_rate": _rate(n_halluc_cases, len(sel)),
        "n_hallucinated_cases": n_halluc_cases,
        "tool_grounding_rate": _rate(n_grounded, n_codes),
        "n_evidence_codes": n_codes,
        "n_grounded_codes": n_grounded,
        "fully_grounded_case_rate": _rate(
            sum(1 for c in sel if not c["grounding"]["ungrounded"]), len(sel)),
        "tool_coverage_rate": _rate(
            sum(1 for c in sel if c["queried_clinvar_and_gnomad"]), len(sel)),
        "classify_acmg_consistency_rate": _rate(
            sum(1 for c in acmg_checked if c["matches_classify_acmg"]), len(acmg_checked)),
        "fallback_rate": _rate(sum(1 for c in sel if c["fallback_triggered"]), len(sel)),
    }


def check_thresholds(agg: dict, thresholds: dict) -> list[str]:
    """Return a list of human-readable threshold failures (empty = pass).

    Keys: ``min_<metric>`` / ``max_<metric>`` over any numeric aggregate field.
    A metric that is ``None`` (no data) fails a min/max check.
    """
    failures: list[str] = []
    for key, bound in thresholds.items():
        if key.startswith("min_"):
            metric, op = key[4:], "min"
        elif key.startswith("max_"):
            metric, op = key[4:], "max"
        else:
            continue
        val = agg.get(metric)
        if val is None:
            failures.append(f"{metric}: no data (threshold {op} {bound})")
        elif op == "min" and val < bound:
            failures.append(f"{metric}={val:.4f} < min {bound}")
        elif op == "max" and val > bound:
            failures.append(f"{metric}={val:.4f} > max {bound}")
    return failures


def class_counts(rows: list[dict]) -> dict[str, int]:
    """Expected-class distribution of labelled rows."""
    return dict(Counter(r["expected_class"] for r in rows if r.get("expected_class")))
