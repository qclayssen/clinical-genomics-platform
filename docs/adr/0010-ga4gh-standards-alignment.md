# ADR-0010 — Align with GA4GH interoperability standards

**Status:** Accepted · **Date:** 2026-07-14

## Context

The platform already emphasises provenance and traceability, but it identified data with local
conventions (a `reference_build` label, file-name-based inputs). The clinical/research genomics
world it targets increasingly expects **GA4GH** interoperability standards — content-based
identifiers (refget, VRS), workflow APIs (WES), and data-access APIs (DRS). Speaking these makes
results portable across sites and tools; ignoring them is a credibility gap for the roles this
project targets. But full adoption of every GA4GH product is far beyond a solo portfolio.

## Decision

Adopt GA4GH standards **incrementally and honestly**, and prove it with one real
implementation rather than a pile of claims:

- **Implement now:** the GA4GH `sha512t24u` computed-digest primitive shared by **refget** and
  **VRS**, dependency-free, verified against the VRS spec's known-answer vector. Use it to
  produce a content-based reference identifier (`ga4gh:SQ.<digest>`).
- **Document alignment:** map the rest (VRS alleles, WES, DRS, Phenopackets, htsget,
  service-info, Crypt4GH, Passport/DUO) in `docs/GA4GH-ALIGNMENT.md`, each marked Implemented /
  Partial / Aspirational / N/A — no overstatement.
- **Chosen next step (not yet wired):** record the reference's `ga4gh:SQ.` ID in run provenance
  alongside `reference_build`.

## Consequences

**Good**
- Reference identity becomes content-based and interoperable — the same sequence yields the
  same ID at any site, reinforcing the traceability story with a recognised standard.
- Demonstrates GA4GH literacy concretely (spec-correct code + test), not just name-dropping.
- The alignment table gives an honest, reviewable roadmap.

**Bad / accepted limitations**
- The VRS allele helper is *simplified* — not a validated VRS identifier without the
  `ga4gh.vrs` library; the doc says so.
- WES/DRS/Phenopackets remain aspirational; the project does not yet expose those APIs.

## Alternatives considered

- **Full VRS via `ga4gh.vrs` + a SeqRepo sequence store** — the correct production path, but a
  heavy dependency (sequence store, normalization) that overshoots a portfolio; deferred, with
  the primitive in place to build on.
- **Expose the pipeline via a WES server now** — high effort, low incremental signal versus a
  content-identifier win that ties into existing provenance; deferred.
- **Do nothing / name-drop GA4GH in the README** — rejected: unearned claims are exactly what
  this project's honesty ethos avoids. Implement one thing properly instead.
