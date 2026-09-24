# Model Card — Variant Interpretation Agent

## Model Overview

| Field | Value |
|---|---|
| **Name** | Clinical Genomics Variant Interpretation Agent |
| **Version** | 0.1.0 |
| **Type** | ReAct-style tool-using agent (not a standalone model) |
| **Task** | ACMG/AMP variant pathogenicity classification |
| **Scope** | Chromosome 20 (GIAB HG002 pipeline scope) |
| **Framework** | Function-calling LLM + deterministic fallback |

## Intended Use

- **Primary**: Post-pipeline interpretation of called variants, producing structured
  ACMG/AMP classifications with evidence citations and reasoning traces.
- **Users**: Bioinformaticians reviewing pipeline output; clinical geneticists as a
  starting point for manual review.
- **NOT intended for**: Direct clinical decision-making without human review, treatment
  recommendations, diagnostic certainty claims.

## Supported LLM Backends

| Backend | Model | Use Case | Cost |
|---|---|---|---|
| Deterministic | N/A (rule-based) | CI, testing, offline; the default for `POST /agent/variant-review` | Free |
| Ollama (local) | llama3.2:3b / phi3:mini | Development, demo | Free (local GPU) |
| OpenAI | gpt-4o-mini | Higher quality | ~$0.01/variant |
| Anthropic | claude-3.5-haiku | Higher quality | ~$0.01/variant |
| Azure AI Foundry | Any OpenAI-compatible deployment | Enterprise/hospital Azure tenancy | Deployment-dependent |
| AWS Bedrock | Any Converse-API-compatible model (default: Claude 3.5 Haiku) | Enterprise/hospital AWS account | Model-dependent |

All six backends implement the same `LLMBackend` interface (`agent/llm.py`); any backend
other than `deterministic` falls back to it automatically if unavailable or if the agent
loop can't complete cleanly — see ADR-0028.

## Limitations

1. **Knowledge base scope**: Only chr20 variants (15 ClinVar records, 18 gnomAD records).
   Variants outside this set will be classified as VUS due to lack of evidence.
2. **Automated evidence only**: Cannot assess clinical criteria requiring patient data
   (de novo status PS2, segregation PP1, phenotype PP4).
3. **No functional prediction**: Does not run computational predictors (REVEL, CADD);
   PP3/BP4 codes are not automatically assigned.
4. **Deterministic fallback is conservative**: Will not classify as Pathogenic without
   ClinVar evidence — a known false-negative bias for novel variants.
5. **Not validated for clinical use**: This is a portfolio demonstration, not an
   accredited clinical tool.

## Known Failure Modes

- **Novel variants** (no ClinVar record, not in gnomAD): Classified as VUS regardless
  of in-silico predictions. Requires manual review.
- **Multi-allelic sites**: Only the first ALT allele is interpreted.
- **Complex variants** (structural variants, CNVs): Not supported; only SNVs and small
  indels are parsed from VCF.
- **LLM hallucination**: The agent may cite non-existent evidence codes if the LLM
  hallucinates; mitigated by validating codes against the ACMG criteria JSON.

## Evaluation

The agent is scored by an automated harness in [`ai-report/eval/`](../eval/README.md)
([ADR-0032](../../docs/adr/0032-agent-evaluation-harness.md)). It plays the role for the
agent that `hap.py` plays for the variant caller. `python ai-report/eval/run_eval.py`
runs any backend over a gold set derived from the KB and writes a provenance-stamped JSON
report (git commit, gold-set SHA-256, backend and model id). `tests/test_agent_eval.py`
gates the deterministic backend in CI.

- **Gold set:** 10 ClinVar variants with ≥ 2★ review status (multi-submitter, no
  conflicts, or expert panel), plus 5 one-star rows (reported only) and 6 unlabelled
  no-ClinVar probes. All come from the same committed KB the agent queries, so the labels
  are **not independent** of the system under test.
- **Metrics:** 5-class and collapsed 3-class accuracy, per-class accuracy, confusion
  matrices, opposite-direction (P/LP ↔ LB/B) errors, hallucinated-citation rate (ClinVar
  accessions or significances the trace's tools never returned), and tool-grounding rate
  (evidence codes supported by tool output).
- **Deterministic baseline:** 3-class 0.90 and 5-class 0.30 on gold (every Pathogenic →
  Likely Pathogenic, as explained below), 0 opposite-direction errors, 0 hallucinated
  citations, grounding 1.0 (38/38). The harness's first run found a default `PM2` the
  scripted backend emitted with no supporting tool evidence; that was fixed (see ADR-0032).
- **Limits:** n = 10 is far too small to estimate performance, and a pass is a
  regression check, not a clinical validation. Real-LLM backends have not been
  benchmarked in CI. LLM-as-judge is never used to decide classification or citation
  correctness.

## Evaluation Results (chr20 known variants — original hand check, superseded by the harness above)

| Variant | Expected | Agent Result | Correct |
|---|---|---|---|
| PRNP E200K (chr20:4699605 G>A) | Pathogenic | Likely Pathogenic | Partial (conservative) |
| PRNP M129V (chr20:4699517 G>A) | Benign | Benign | ✓ |
| JAG1 R468* (chr20:10637684 C>T) | Pathogenic | Likely Pathogenic | Partial (conservative) |
| GNAS R201C (chr20:58909365 C>T) | Pathogenic | Likely Pathogenic | Partial (conservative) |
| AURKA F31I (chr20:56369542 T>A) | Benign | Benign | ✓ |
| CDH22 A238T (chr20:45900123 G>A) | VUS | VUS | ✓ |

**Note**: "Likely Pathogenic" instead of "Pathogenic" for known pathogenic variants is
expected — the automated evidence (PS1 + PM2 + PP5 = 1 Strong + 1 Moderate) correctly
maps to Likely Pathogenic per ACMG rules. Full Pathogenic requires additional evidence
(functional studies PS3, de novo PS2) that automated tools cannot provide.

## Safety Measures

- Mandatory review banner on all output (code-enforced, not prompt-dependent)
- Treatment/diagnosis language automatically scrubbed
- VUS variants flagged with explicit uncertainty statement
- Full reasoning trace for audit
- Evidence codes required — cannot produce classification without citations
- Human-in-the-loop: classification is a *draft* for clinical geneticist review

## Ethical Considerations

- This agent does not replace clinical expertise — it assists by structuring evidence.
- Conservative bias (under-classifying) is preferred over aggressive bias for safety.
- All output clearly marked as AI-generated requiring expert review.
- No patient data is used or stored by the agent itself.
