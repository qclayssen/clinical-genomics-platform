# ADR-0001 — Scope to GIAB HG002, chromosome 20, germline SNVs

**Status:** Accepted · **Date:** 2026-05-01

## Context

This is a solo portfolio project with a few-weekends budget. The temptation is to attempt a
full clinical WGS platform across every variant type and assay. That path never finishes and
produces shallow, unconvincing coverage. A hiring manager trusts *depth on a well-chosen
slice* far more than breadth that was clearly never run to completion.

We also need a way to *prove* correctness, which requires a dataset with a published,
authoritative "right answer."

## Decision

Restrict the initial scope to a single, deliberately narrow target:

- **Sample:** GIAB HG002 / NA24385 (a public, consented reference individual).
- **Region:** chromosome 20 only (and a ~1 Mb slice for the CI/test profile).
- **Analysis:** germline single-nucleotide variant (SNV) calling.

Everything else (INDELs, whole genome, somatic calling, immune repertoire) is explicitly
out of scope for v1 and noted as a designed-for extension.

## Consequences

**Good**
- Inputs are small enough to run on a laptop or a modest cloud instance.
- A gold-standard truth set exists for this exact sample, enabling real validation
  ([ADR-0003](0003-truth-set-validation.md)).
- The project is genuinely finishable and demoable end-to-end.

**Bad / accepted limitations**
- Performance is proven on chr20 only; no genome-wide claim is made (stated in
  `docs/VALIDATION.md`).
- INDEL performance is reported for information but not gated on.

## Alternatives considered

- **Whole genome, HG002** — rejected: data volume and runtime blow the budget with no extra
  demonstration value for a portfolio.
- **A tumour/normal somatic pair** — rejected: more clinically flashy but far harder to
  validate cleanly and to finish solo.
- **MiXCR immune repertoire instead** — kept as a *future* extension
  ([ADR-0002](0002-nextflow-dsl2-pipeline.md) keeps the pipeline assay-agnostic), not the v1
  focus, because germline SNV + truth-set benchmarking tells the clearest correctness story.
