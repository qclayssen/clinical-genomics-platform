# ADR-0003 — Validate by benchmarking against a truth set (hap.py)

**Status:** Accepted · **Date:** 2026-05-06

## Context

The single most important claim a clinical-grade pipeline can make is *"here is how accurate
it is."* Many portfolio projects skip this: they produce a VCF and stop. Without a measured
accuracy figure there is nothing to distinguish a correct pipeline from a subtly broken one,
and nothing an accreditation reviewer could sign.

## Decision

Make **truth-set benchmarking a first-class pipeline stage**, not an afterthought. Compare
each run's VCF to the **GIAB HG002 v4.2.1** benchmark using **`hap.py`** (vcfeval engine),
restricted to the published **high-confidence BED**, and compute **precision, recall, F1**.
Define an explicit **acceptance criterion (SNV F1 ≥ 0.99)** recorded per run as
`validation_pass`.

## Consequences

**Good**
- The pipeline reports a *measured* accuracy, framed like a lab's analytical validation
  (`docs/VALIDATION.md`).
- Downstream automation (DB flag, dashboard, AI report) can trust and surface a single
  pass/fail signal.
- Any regression (a bad config change) shows up as a metric drop in CI/dashboard rather than
  silently shipping.

**Bad / accepted limitations**
- Accuracy is only claimed within the high-confidence regions and on chr20
  ([ADR-0001](0001-scope-giab-hg002-chr20.md)); low-complexity regions are out of scope.
- `hap.py` adds a tool and a comparison step to the runtime.

## Alternatives considered

- **No formal validation, eyeball the VCF** — rejected: this is exactly the gap that makes a
  project read as a toy.
- **`bcftools isec` for a rough overlap** — rejected: doesn't handle representation
  differences (how the same variant can be written two ways) the way `hap.py`/vcfeval does,
  so the numbers would be misleadingly pessimistic.
- **A fixed threshold with no truth set** — impossible without ground truth; the truth set is
  the whole point.
