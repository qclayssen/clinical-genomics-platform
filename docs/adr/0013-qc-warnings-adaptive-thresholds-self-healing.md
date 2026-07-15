# ADR 0013: QC Warnings with Adaptive Thresholds and Self-Healing

## Status

Accepted

## Date

2026-07-15

## Context

The platform previously relied on a binary pass/fail check (SNP F1 ≥ 0.99) and basic job-failure alarms. There was no early warning when QC metrics drifted toward failure, no automated remediation beyond Nextflow's exit-code retries, and no intelligent recovery from complex failures. Operators discovered issues only after full pipeline failure, increasing turnaround time and requiring manual intervention for every quality event.

Clinical genomics pipelines need proactive quality monitoring: detecting degradation before it reaches the failure threshold, automatically attempting recovery for known failure patterns, and escalating to operators only when automated remediation is insufficient.

## Decision

We implement a comprehensive QC warning layer with four key capabilities:

### 1. Multi-Metric Threshold Evaluation

- Monitor 6 QC metrics: percent_duplication, q30_rate, reads_filtered_percent, snp_f1, snp_precision, snp_recall
- Each metric has warn and fail thresholds with direction semantics (higher_is_worse, lower_is_worse)
- Configuration lives in `pipeline/conf/qc_thresholds.yaml` — single source of truth
- New Nextflow process `QC_EVALUATE` runs after HAPPY_BENCHMARK, emitting `qc_warnings.json`

### 2. Adaptive Thresholds (Mean ± 2σ)

- When ≥ 20 historical runs exist, thresholds are computed as mean ± 2σ from run history
- Below 20 runs: fall back to bootstrap defaults from configuration
- Edge cases handled: σ=0 (identical values) falls back to bootstrap, thresholds clamped to [0,1]
- Tighter thresholds emerge naturally as the pipeline establishes a quality baseline

### 3. Multi-Level Self-Healing

- **Retry profiles**: Progressively stricter fastp parameters per attempt (phred 15→20→25, length 50→60→75)
- **Escalating quarantine**: Soft quarantine on first failure (blocks reports), hard quarantine on consecutive failures (moves data, full block)
- **Step Functions Choice states**: Deterministic routing for known failure patterns (OOM → more memory, timeout → longer duration, QC breach → stricter params)
- **AI healer Lambda**: Ollama-based diagnosis for ambiguous failures, with rule-based fallback

### 4. Notify-Then-Auto-Execute

- After healer recommendation: SNS notification to operators with proposed action
- Configurable wait period (default 10 minutes) before auto-execution
- Operators can approve, override, or let the timeout trigger automatic remediation
- Maximum 2 self-healing attempts before escalation to prevent infinite loops

### Warning Surfaces

- **CloudWatch**: 6 custom metric alarms in CGP/QC namespace with SNS actions
- **MultiQC**: Conditional formatting (green/orange/red) using `table_cond_formatting_rules`
- **DynamoDB**: QC_WARNING records with full evaluation detail
- **Metabase**: Three dashboard views (warning frequency, metric vs threshold, quarantine status)

## Consequences

### Positive

- Early detection of quality degradation before full failure
- Reduced operator toil through automated recovery of common failure modes
- Traceable quarantine history for sample quality tracking
- Adaptive thresholds tighten naturally as pipeline matures
- All components testable independently (212 Python tests + 66 CDK tests)

### Negative

- Increased system complexity (new Nextflow process, Lambda, Step Functions states)
- Adaptive thresholds require accumulating history before becoming effective
- AI healer depends on Ollama availability (mitigated by rule-based fallback)
- 10-minute auto-execute timeout may be too short for some operator workflows

### Risks Mitigated

- **Infinite healing loops**: CheckHealingLimit guard (max 2 attempts)
- **LLM hallucination**: Fixed action set + response validation + rule-based fallback
- **Hard quarantine lock-in**: Explicit release_quarantine admin action
- **Threshold misconfiguration**: Schema validation with meaningful error messages + property tests

## Components Added

| Component | Path | Purpose |
|-----------|------|---------|
| QC Thresholds Config | `pipeline/conf/qc_thresholds.yaml` | Bootstrap defaults, retry profiles, quarantine rules |
| Threshold Loader | `pipeline/bin/qc_thresholds.py` | Typed config with validation |
| Adaptive Calculator | `pipeline/bin/qc_adaptive.py` | Mean ± 2σ with bootstrap fallback |
| QC Evaluator | `pipeline/bin/qc_evaluate.py` | Parses QC outputs, evaluates all metrics |
| QC Evaluate Module | `pipeline/modules/qc/qc_evaluate.nf` | Nextflow process wired after HAPPY_BENCHMARK |
| MultiQC Config | `pipeline/assets/multiqc_config.yaml` | Conditional formatting rules |
| Retry Profiles | `pipeline/conf/retry_profiles.config` | Attempt-dependent fastp parameters |
| Quarantine Manager | `pipeline/bin/quarantine.py` | Soft/hard quarantine with escalation |
| Healer Lambda | `lambdas/healer/handler.py` | AI diagnostics with rule-based fallback |
| CloudWatch Alarms | `infra/lib/observability-stack.ts` | 6 QC metric alarms in CGP/QC namespace |
| Self-Healing States | `infra/lib/orchestration-stack.ts` | Choice states + notify-wait pattern |
| QC Warnings Table | `db/schema.sql` | Postgres table + 3 Metabase views |
| DynamoDB Model | `lambdas/shared/models.py` | QC_WARNING record type |

## References

- MultiQC conditional formatting: https://multiqc.info/docs/getting_started/config/
- Step Functions Choice state: https://docs.aws.amazon.com/step-functions/latest/dg/amazon-states-language-choice-state.html
- Adaptive threshold theory: Shewhart control charts (mean ± kσ)
