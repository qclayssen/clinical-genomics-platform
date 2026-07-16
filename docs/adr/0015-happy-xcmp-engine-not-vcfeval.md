# ADR-0015 — Use hap.py's xcmp engine, not vcfeval

**Status:** Accepted · **Date:** 2026-07-15
**Supersedes:** the engine choice in [ADR-0003](0003-truth-set-validation.md) (vcfeval); the rest
of ADR-0003 — benchmarking as a first-class stage, the acceptance criterion, the alternatives
rejected — stands unchanged.

## Context

ADR-0003 chose `hap.py` with the **vcfeval** comparison engine. Running the first real,
non-stub validation against real GIAB HG002 chr20 reads surfaced that this was never actually
runnable: the pinned container (`quay.io/biocontainers/hap.py:0.3.15--py27hcb73b3d_0`) does not
bundle `rtg-tools`, which vcfeval requires as an external dependency. The process failed with
`rtg: command not found` — not a platform/emulation issue, a missing binary in the image itself,
so it would fail identically on any host architecture.

The historical Docker Hub image that does bundle `rtg-tools` (`pkrusche/hap.py`) is built with a
legacy manifest format current Docker no longer accepts (`media type ... no longer supported`),
so it cannot be pulled at all.

## Decision

Run `hap.py` with its **default `xcmp` engine** instead of `--engine vcfeval`. `xcmp` is hap.py's
original comparison engine, fully self-contained in the pinned biocontainers image, and is a
well-established GIAB benchmarking method in its own right — the GIAB/PrecisionFDA community used
it as the default for years before vcfeval became common. `docs/VALIDATION.md`'s methodology
section, the `HAPPY_BENCHMARK` module, and other docs referencing "vcfeval" are updated to say
`xcmp`.

## Consequences

**Good**
- Real validation is actually runnable with the currently pinned, currently pullable container —
  no dependency on an image that can't be fetched.
- `xcmp` remains a scientifically defensible comparison method; the F1 ≥ 0.99 acceptance
  criterion and its interpretation are unaffected.

**Bad / accepted limitations**
- `xcmp`'s representation-matching is less sophisticated than vcfeval's for some complex/nearby
  variant representations, which can make precision/recall *slightly* more conservative than
  vcfeval on the same calls. Not expected to matter at chr20 SNV scale, but noted for anyone
  reproducing these numbers with a different engine.
- If a future container image bundling both `hap.py` and `rtg-tools` becomes available (or is
  built in-repo), switching back to vcfeval is a one-line change plus a new ADR.

## Alternatives considered

- **Build a custom image with rtg-tools added** — rejected for now: adds a maintenance burden
  (an unpinned, self-built image) disproportionate to a portfolio project's needs; revisit if
  vcfeval-specific precision matters later.
- **Skip real validation until a working vcfeval setup is found** — rejected: `xcmp` gives a real,
  honestly-labeled measured result now rather than blocking on tooling.
