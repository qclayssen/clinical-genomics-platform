# Containers

Each pipeline stage runs in its own pinned container. Two sourcing strategies, both
reproducibility-first:

- **Biocontainers by digest** — the Nextflow modules reference upstream Biocontainer
  images pinned to a specific tag/build (see each `modules/**/*.nf`). Pin to the
  `@sha256:` digest in a real deployment so an image can never silently change under you.
- **Local helper image** (`Dockerfile.tools`) — a small image bundling the
  dependency-free helper scripts (`build_metrics.py`, `ingest_metrics.py`) plus
  `bcftools`, used by the export/ingest steps.

Pinning by digest, not tag, is the accreditation-relevant point: "the software that
produced this result is byte-for-byte identifiable."
