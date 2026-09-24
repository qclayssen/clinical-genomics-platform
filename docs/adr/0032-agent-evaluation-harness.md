# ADR-0032 — Evaluation harness for the variant-interpretation agent

**Status:** Accepted · **Date:** 2026-09-24 · **Relates to:** [ADR-0003](0003-truth-set-validation.md) (truth-set validation), [ADR-0008](0008-guardrails-human-in-the-loop.md) (guardrails), [ADR-0014](0014-agentic-variant-interpretation.md) (the agent), [ADR-0028](0028-azure-bedrock-backends-and-fhir-intake.md) (backends)

## Context

The variant caller has an objective acceptance test: `hap.py` against the GIAB truth set,
with SNV F1 ≥ 0.99 ([ADR-0003](0003-truth-set-validation.md)). The interpretation agent
([ADR-0014](0014-agentic-variant-interpretation.md)) had no equivalent. Its model card
held a six-row hand-written table, `DESIGN.md` described the evaluation only in prose, and
nothing in CI would fail if a prompt, rule or backend change began misclassifying variants
or citing ClinVar evidence that no tool had returned. Swapping the backend (Ollama, OpenAI,
Anthropic, Azure, Bedrock, per ADR-0028) had no measurable consequence.

Two failure modes matter for an LLM agent in this domain:

1. **Wrong classification.** The worst case is an *opposite-direction* error: P/LP called
   LB/B, or the reverse.
2. **Fabricated grounding.** The agent cites a ClinVar accession, a ClinVar significance
   or an ACMG evidence code that none of its tool calls produced. A human reviewer who
   trusts the trace is misled.

## Decision

Add `ai-report/eval/`, a harness that runs the agent over a committed gold set and gates on
metrics set in config.

### Gold set

- **Derived, not hand-typed.** `build_gold_set.py` reads the committed KB
  (`ai-report/agent/data/chr20_knowledge.db`, *"ClinVar VCV 2026-06 subset"*, KB v1.0.0).
  `--check` and a pytest test fail if `gold_set.jsonl` drifts from the KB.
- **Selection criterion (`gold`, gated):** a ClinVar review status that ClinVar rates
  **≥ 2 stars**, i.e. `criteria_provided_multiple_submitters_no_conflicts`,
  `reviewed_by_expert_panel` or `practice_guideline`. Eligibility is decided on the status
  string, not on the KB's `review_stars` column, which uses a shifted scale.
- **`silver` (reported, not gated):** 1★ single-submitter records.
- **`probe` (no label):** 3 gnomAD-only KB rows and 3 synthetic positions inside annotated
  chr20 genes, all absent from the ClinVar table. They are used only to catch fabricated
  ClinVar citations and ungrounded codes.
- Every report pins the gold set by SHA-256.

### Metric set

| Metric | Gated? |
|---|---|
| 5-class accuracy (P/LP/VUS/LB/B) | **Reported only**, see below |
| 3-class accuracy (P/LP · VUS · LB/B) | yes, gold |
| Per-class accuracy (recall per expected class), 5- and 3-class confusion matrices | reported |
| Opposite-direction errors (P/LP ↔ LB/B) | yes, gold, **= 0** |
| Hallucinated-citation rate: a ClinVar accession or significance in the final summary that no `query_clinvar` observation in the trace returned | yes, all tiers, **= 0** |
| Tool-grounding rate: share of final evidence codes supported by a tool observation in the same trace (codes no tool can produce, e.g. PS3/PP3, count as ungrounded) | yes, all tiers |
| Tool coverage (both ClinVar and gnomAD queried), `classify_acmg` consistency, fallback rate | coverage gated; others reported |

5-class accuracy is not gated because the only automated evidence is ClinVar plus gnomAD.
For a ≥ 2★ Pathogenic variant that gives PS1 + PM2 + PP5, which the ACMG combining rules
call **Likely** Pathogenic. Full Pathogenic needs PS2/PS3-type evidence that no tool
supplies. A 5-class gate would therefore only encode this known, documented and
deliberately conservative bias.

### Thresholds (`ai-report/eval/eval_config.json`)

| Gate | Tiers | Thresholds |
|---|---|---|
| `gold_classification` | gold | `accuracy_3class ≥ 0.90`, `opposite_direction_errors ≤ 0` |
| `citation_integrity` | gold + silver + probe | `hallucinated_citation_rate ≤ 0.0`, `tool_grounding_rate ≥ 1.0`, `tool_coverage_rate ≥ 1.0` |

These are **regression floors at the deterministic backend's measured baseline**, not
clinical acceptance criteria. Baseline at commit `633cd77`: gold n = 10, 3-class 0.90,
5-class 0.30 (all six P → LP; the single LP → VUS), 0 opposite-direction errors,
0 hallucinated citations across all 21 rows, grounding 38/39 = 0.974 — rising to
38/38 = 1.0 once the first finding below was fixed, after which the grounding floor was
raised from 0.95 to 1.0.

### Backends

- **Default and CI: `deterministic`**, the scripted ReAct backend in `agent/llm.py`. It
  exercises the real loop, tool registry, `final_answer` validation and safety scrubbing,
  and runs offline and reproducibly with no GPU, network or AWS. `tests/test_agent_eval.py`
  runs it and asserts every gate.
- `--backend` accepts any backend `create_backend()` supports, plus `interpreter` (the
  no-LLM `DeterministicInterpreter`). By default a run scores the post-fallback result,
  as `interpret.py` and the REST API do, and reports the fallback rate. `--no-fallback`
  scores the raw agent output instead.
- **LLM-as-judge is out of scope for classification, now and later.** If one is ever added,
  it may only grade the *wording* of the summary (clarity, absence of advice language).
  It must never decide whether a classification or a citation is correct. Those checks
  stay rule-based against the gold labels and the tool trace, because a judge model can
  share the same hallucinations as the model it grades.

## Limitations (accepted)

- **Small n.** The roadmap target was 50–100 variants. The committed KB has 15 ClinVar
  records, 10 of them ≥ 2★, and this change made no network downloads and invented no
  labels. At n = 10, one error moves accuracy by 10 points. The gold set has no VUS or LB
  rows, so those per-class numbers are `null`.
- **Labels are not independent of the system under test.** The agent reads the same
  `clinvar` table the labels come from. The harness measures whether the agent *faithfully
  carries* ClinVar evidence through the ACMG rules and cites only what its tools returned.
  It does not measure performance on novel variants.
- **The deterministic backend is scripted.** A passing CI run proves the harness and the
  loop, not the quality of any real LLM. Real-model numbers exist only for runs someone
  performs with credentials, and they should be kept as provenance-stamped reports.
- **The citation check is lexical.** It catches ClinVar accessions (`VCV/RCV/SCV…`,
  "ClinVar ID n") and "ClinVar reports … as <class>" claims in the final summary. A
  paraphrased fabrication could get past it.
- **KB accessions not re-verified.** The `VCV…` IDs come from the repo's embedded subset
  and were not checked against live ClinVar in this change.
- **Not a clinical validation.** Nothing here makes the agent fit for diagnostic use. The
  human-review guardrails of ADR-0008 still apply to every output.

### First finding

The harness flagged one ungrounded evidence code on its first run. For probe
`chr20:5555555 G>T` (gnomAD AF 0.001, which triggers no frequency code), the scripted
backend's `_gather_evidence_codes` falls back to a default `["PM2"]`, and no tool output
supports that code. It stayed within the original 0.95 grounding floor. It was fixed in the
same change set: the default was removed, `final_answer` now accepts an empty evidence
list only for Uncertain Significance ("no ACMG criteria met"), a regression test covers
both, and the floor was raised to 1.0.

## What would change this decision

- A real ClinVar/gnomAD extract for chr20 (implementing `build_chr20_knowledgebase.py
  --download`) grows the gold set: rerun `build_gold_set.py`, re-baseline, and raise the
  thresholds.
- If a real LLM backend becomes the default for any user-facing path, its
  provenance-stamped eval report must pass the same gates before that switch.
- Adding evidence tools (e.g. in-silico predictors for PP3/BP4) changes both the grounding
  rules in `eval_metrics._code_grounded` and the case for gating 5-class accuracy.

## Consequences

**Good**
- The agent now has an objective, CI-enforced regression test that plays the same role
  `hap.py` plays for the caller, and backends can be compared on identical inputs with
  provenance.
- Fabricated ClinVar citations and ungrounded evidence codes are measured and gated.
  Before, they were only mentioned in the model card as a risk.

**Bad / accepted**
- The headline numbers are easy to over-read. Every report carries a disclaimer, and the
  README and model card state the n and the non-independence of the labels.
