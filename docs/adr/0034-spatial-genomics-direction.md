# ADR-0034 — Spatial transcriptomics: a sketched direction, deliberately not built

**Status:** Proposed (direction note, not implemented — and not scheduled) · **Date:** 2026-09-24

## Context

The platform is scoped to germline SNV calling on GIAB HG002 chr20
([ADR-0001](0001-scope-giab-hg002-chr20.md)). *Spatial transcriptomics* measures which genes
are expressed **and where** in a tissue section: spot-based capture arrays (Visium-style, each
spot covers several cells) or in-situ imaging of targeted genes (Xenium-style, single-cell /
sub-cellular). Multi-omics teams increasingly ask how a genomics platform would stretch to it.
This ADR records how the existing patterns *could* carry over, and why nothing is being built.
No code, schema, infrastructure, or pipeline changes accompany it.

## Direction (if it were ever built)

- **New stages, new module group.** A separate `pipeline/modules/spatial/` group behind an assay
  selector, following the one-process-per-module convention
  ([ADR-0002](0002-nextflow-dsl2-pipeline.md)). Stages would be: read/image QC (spots or cells
  detected, reads or transcripts per spot/cell, genes detected, fraction of reads under tissue),
  image registration of the tissue photo to the capture array, **cell segmentation** (drawing
  cell boundaries on the image so transcripts can be assigned to cells), and a count matrix
  (genes × spots or cells) with an x/y coordinate for every column. Vendor tools (e.g. Space
  Ranger / Xenium output bundles) would be wrapped as pinned containers
  ([ADR-0009](0009-docker-pinned-by-digest.md)), not reimplemented.
- **Spatial-coordinate data model, alongside — not inside — the insert-only stores.** Large
  matrices and images belong in object storage as files (e.g. AnnData / Zarr), referenced by
  checksum. Only run-level records and summary QC would go into the existing insert-only
  stores, keeping their current guarantees and stated limits
  ([ADR-0005](0005-insert-only-postgres.md), [ADR-0012](0012-dynamodb-primary-store.md),
  [ADR-0031](0031-dynamodb-streams-audit-sink-accepted-limitation.md)). A re-segmentation
  would be a new run record, never an edit.
- **Visualisation.** Metabase ([ADR-0006](0006-metabase-dashboard.md)) suits run-level QC
  trends but cannot render tissue images or overlay expression on coordinates; that needs a
  dedicated viewer (e.g. an image-tile viewer in `web/`). This is new front-end work, not a
  dashboard tweak.
- **Validation analog — weaker, and it must be said.** There is **no GIAB-equivalent truth
  set** for spatial expression: no public sample with an authoritative, per-location "right
  answer" to score an F1 against. The honest substitutes are reproducibility (replicate or
  serial sections agree), concordance with an orthogonal method on the same tissue (bulk or
  single-cell RNA-seq, or known marker-gene localisation), and segmentation checks against a
  small hand-annotated image set. None would support a hard acceptance gate like SNV
  F1 ≥ 0.99 ([ADR-0003](0003-truth-set-validation.md)); any spatial `VALIDATION.md` section
  would have to call its criteria *consistency checks*, not accuracy.
- **Provenance carries over; its known gaps would carry over too.** The same stamp (git commit,
  pipeline version, reference/annotation version, SHA-256 of outputs) would apply, plus the
  segmentation model and its parameters, which change results as much as the caller does. The
  gaps already documented for the SNV stamp (inputs not checksummed, no container digest or
  tool version in the stamp — see [VALIDATION.md](../VALIDATION.md) §6) would apply unchanged
  until closed.
- **AI guardrails carry over unchanged in principle.** The model would see only a summary
  metrics file, never images or matrices, and every draft would pass `enforce_guardrails()`
  (`ai-report/guardrails.py`) and human sign-off ([ADR-0008](0008-guardrails-human-in-the-loop.md)).
  The current model is fine-tuned on SNV metrics ([ADR-0007](0007-qlora-small-open-model.md)),
  so a spatial summary would need new training data and its own evaluation — not a reuse.

## Decision

**Do not build any of this now.** Keep this ADR at `Proposed` as a direction note only.

## Why not now

- **Focus is the product.** ADR-0001's premise is that depth on one finished, validated slice
  beats breadth that was never run to completion. Spatial is a genuinely different domain —
  imaging, segmentation, expression rather than variants — not another variant type.
- **An unfinished large build weakens the portfolio.** This is at least an L effort with no
  truth set to close it out; a half-built spatial branch would read as the opposite of the
  "scoped so one person finishes it" discipline.
- **It is not next in line.** The planned second assay is the immune-repertoire (MiXCR) branch
  (ADR-0001 alternatives, ADR-0002), which is itself **not yet built**. The claim that the
  spine is assay-agnostic should be proven there, on a closer domain, before a further one is
  considered.

## What would change this

The immune-repertoire branch landing and validated on the shared spine, *and* a concrete need
(a role, collaborator, or dataset) for spatial work. At that point, write a new ADR that
accepts a narrowed version of this direction; do not flip this one to Accepted unedited.

## Consequences

**Good**
- The spatial question has a written, reasoned answer, with the missing truth set named rather
  than glossed over.
- Scope discipline is shown as a deliberate choice, not an omission.

**Bad / accepted**
- The platform has no spatial capability, and nothing in this ADR has been prototyped or tested.
