# Agent evaluation harness ("hap.py for the LLM")

Scores the variant-interpretation agent (`ai-report/agent/`) against a committed gold
set. `hap.py` benchmarks the variant caller against GIAB; this harness benchmarks the
interpretation agent against ClinVar, and also checks that every citation it makes can
be traced to a tool call. Decision record: [ADR-0032](../../docs/adr/0032-agent-evaluation-harness.md).

> **Not a clinical validation.** The gold set is tiny and comes from the same local
> knowledge base the agent queries. A passing run means "no regression, no fabricated
> citations on this set". It does **not** mean the agent's classifications are clinically valid.

## Run it

```bash
python ai-report/eval/run_eval.py                        # deterministic backend, offline
python ai-report/eval/run_eval.py --backend interpreter  # the no-LLM DeterministicInterpreter
python ai-report/eval/run_eval.py --backend anthropic --out results/agent_eval/anthropic.json
python ai-report/eval/run_eval.py --no-fallback          # score raw agent output, not post-fallback
```

Exit code: `0` all gates pass · `1` a gate failed · `2` harness error. The JSON report
(default `results/agent_eval/report.json`, gitignored) holds a provenance stamp (git
commit + dirty flag, gold-set / config / knowledge-base SHA-256, KB metadata, backend,
model id, Python version, UTC time), per-tier aggregates, 5- and 3-class confusion
matrices, per-case scores, and the full agent traces.

`pytest tests/test_agent_eval.py` runs the harness on the deterministic backend and
asserts the gates in [`eval_config.json`](eval_config.json).

## Gold set — `gold_set.jsonl`

| Field | Value |
|---|---|
| **Source** | `ai-report/agent/data/chr20_knowledge.db`, `clinvar` table, the repo's embedded ClinVar subset. Its `metadata` table says *"ClinVar VCV 2026-06 subset"*, KB v1.0.0, built 2026-07-15 by `scripts/build_chr20_knowledgebase.py` |
| **Derivation** | `python ai-report/eval/build_gold_set.py` (deterministic). `--check` fails if the committed file has drifted from the KB, and the pytest suite runs that check |
| **Selection criterion (`gold` tier)** | ClinVar review status **≥ 2 stars**: `criteria_provided_multiple_submitters_no_conflicts` or `reviewed_by_expert_panel`. Note: the KB's `review_stars` column stores 3 for the multi-submitter status, where ClinVar's own scale gives it 2★ (and expert panel 3★). The criterion is the same under either scale, but it is the review-status *string* that decides eligibility |
| **Pinned by** | SHA-256 of the file, recorded in every report |

| Tier | n | Label | Scored? | Gated? |
|---|---:|---|---|---|
| `gold` | 10 | ClinVar ≥ 2★ (6 P, 1 LP, 3 B) | yes | yes: classification + citation integrity |
| `silver` | 5 | ClinVar 1★ single submitter (3 VUS, 1 LP, 1 P) | yes, reported only | citation integrity only |
| `probe` | 6 | **none**. 3 gnomAD-only KB rows + 3 synthetic positions inside annotated chr20 genes, all absent from the ClinVar table | no accuracy | citation integrity only |

### Honest limitations of the gold set

- **n is small, and far below the 50–100 the roadmap asked for.** The committed KB holds
  only 15 ClinVar records, and just 10 of them are ≥ 2★. Growing the set means extending
  the KB, which needs a real ClinVar/gnomAD download
  (`build_chr20_knowledgebase.py --download` is not implemented yet). This change
  deliberately made no network downloads and invented no labels. With n = 10, a single
  misclassification moves accuracy by 10 points, so treat every number as a regression
  signal, not an estimate of performance.
- **Classes are unbalanced and incomplete.** No gold row is VUS or Likely Benign, so
  per-class accuracy for those classes is `null`.
- **The labels are not independent of the system under test.** The agent reads the
  same `clinvar` table the labels come from. The harness measures whether the agent
  *faithfully carries* ClinVar evidence through the ACMG rules and its citations. It
  does not measure whether the agent can classify variants ClinVar has never seen.
- **The accessions were not re-verified.** The `VCV…` IDs and review statuses are
  copied from the repo's embedded subset. They were not checked against live ClinVar
  in this change (no network access).
- Probe positions are **synthetic** and are never presented as real variants.

## Metrics

Defined in [`eval_metrics.py`](eval_metrics.py). Every function is pure and unit-tested.

| Metric | Definition |
|---|---|
| `accuracy_5class` | Exact match over P / LP / VUS / LB / B |
| `accuracy_3class` | Match after collapsing to P/LP · VUS · LB/B |
| `per_class_5` / `per_class_3` | Recall per *expected* class |
| `confusion_5class` / `confusion_3class` | Rows are expected, columns are predicted (with an `INVALID` column) |
| `opposite_direction_errors` | Count of P/LP ↔ LB/B swaps, the clinically dangerous error |
| `hallucinated_citation_rate` | Share of cases whose final summary cites a ClinVar accession (`VCV/RCV/SCV…` or "ClinVar ID n") that no `query_clinvar` observation in the trace returned, or asserts a ClinVar significance that the tool did not return |
| `tool_grounding_rate` | Share of final evidence codes that some tool observation in the same trace supports: PS1/PP5 need a returned P/LP ClinVar record, BP6 needs B/LB, BA1/BS1/BS2/PM2 need the returned gnomAD AF (or the tool's own `acmg_frequency_codes`), PVS1 needs a returned truncating `hgvs_p`. Codes no tool can produce (PS2, PS3, PP3, …) are ungrounded by definition |
| `tool_coverage_rate` | Share of cases in which both `query_clinvar` and `query_gnomad` were called |
| `classify_acmg_consistency_rate` | Share of cases whose final class matches the `classify_acmg` tool output |
| `fallback_rate` | Share of cases where the ReAct loop fell back to the deterministic interpreter |

## Baseline (deterministic backend, commit `633cd77`)

| Tier | acc 5-class | acc 3-class | opposite-direction | hallucinated | grounding |
|---|---:|---:|---:|---:|---:|
| gold (n=10) | 0.30 | 0.90 | 0 | 0.00 | 1.00 |
| silver (n=5) | 0.60 | 0.60 | 0 | 0.00 | 1.00 |
| probe (n=6) | n/a | n/a | 0 | 0.00 | 0.875 |
| **all (n=21)** | | | 0 | **0.00** | **0.974** (38/39) |

What these numbers say:

- **All six gold Pathogenic variants → Likely Pathogenic.** This is the documented
  conservative bias. ClinVar ≥ 2★ plus gnomAD gives PS1 + PM2 + PP5 (1 Strong,
  1 Moderate, 1 Supporting), and the ACMG rules call that Likely Pathogenic. Reaching
  Pathogenic needs PS3/PS2-type evidence that no tool supplies, which is why 5-class
  accuracy is reported but not gated.
- **The single gold LP (JAG1 p.Gly277Ser) → VUS.** For ClinVar LP the backend derives
  only PP5 (not PS1), and PP5 + PM2 meets no ACMG rule.
- **One ungrounded code:** probe `chr20:5555555 G>T` (gnomAD AF 0.001, which triggers
  no frequency code). The scripted `DeterministicBackend` (`agent/llm.py`,
  `_gather_evidence_codes`) falls back to a default `["PM2"]` when no tool produced
  evidence, and no tool output supports that code. The harness exists to catch this
  kind of issue. It is recorded, not fixed, in this change.
