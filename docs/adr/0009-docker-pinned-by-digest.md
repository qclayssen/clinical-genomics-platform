# ADR-0009 — Containerise every step and pin images by digest

**Status:** Accepted · **Date:** 2026-05-27

## Context

Reproducibility is a hard requirement: the same input must produce the same output, and a
result from six months ago must be reconstructable with the *exact* software that produced
it. Bioinformatics tools are notoriously sensitive to version changes, and "latest" tags
silently move.

## Decision

Run **every pipeline step in its own container** (Biocontainers where available), and **pin
images by immutable digest (`@sha256:…`)** in production rather than by mutable tag. The
local helper image (`docker/Dockerfile.tools`) bundles the dependency-free scripts and is
pinned the same way. Container identity is captured in the provenance record for each run.

## Consequences

**Good**
- "The software that produced this result is byte-for-byte identifiable" — a direct
  accreditation/traceability win.
- Eliminates "works on my machine"; local and cloud runs use identical images.
- A tool upgrade becomes a deliberate, reviewable change (new digest) that triggers
  re-validation ([ADR-0003](0003-truth-set-validation.md)).

**Bad / accepted limitations**
- Digest pinning is less readable than tags and requires a deliberate update process.
- Container pulls add startup latency and require a registry to be reachable.

## Alternatives considered

- **Conda/mamba environments, no containers** — reproducible-ish but far more environment
  drift and no clean cloud-execution story with Batch.
- **Pinning by tag (e.g. `:1.6.1`)** — better than `latest`, but tags can be re-pushed;
  digests are the only truly immutable reference.
- **A single fat image with all tools** — simpler to manage but couples unrelated tool
  versions and bloats every job; per-step images keep changes isolated.
