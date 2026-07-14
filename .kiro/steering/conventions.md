# Coding Conventions

## Nextflow

- **One process per module file**, nf-core style (`pipeline/modules/<group>/<tool>.nf`).
- Every process has a `stub:` block so `-stub` runs offline, and a `container` directive.

## Docker

- **Pin Docker images by digest** (`@sha256:…`) in production; Biocontainers where available.
- Container identity is captured in provenance.

Reference: #[[file:docs/adr/0009-docker-pinned-by-digest.md]]

## Infrastructure (CDK)

- **CDK guardrail tests must stay green** — they encode accreditation-relevant invariants (bucket versioning, public-access block, TLS-only, IAM deny-delete on raw/results).

Reference: #[[file:infra/test/stacks.test.ts]]

## Python / Tests

- **Change behaviour → update tests + provenance** in the same change.
- Python logic is covered by `tests/test_build_metrics.py`.

## Verified vs. needs-environment

- **Verified running:** `pytest` suite, metrics/provenance builder, `infer.py --offline`, CPU LoRA smoke test.
- **Needs Nextflow + Docker:** full genomics pipeline on real GIAB data.
- **Needs AWS account:** `cdk deploy` (CI only runs `cdk synth`).
- **Needs GPU:** full QLoRA fine-tune (CPU smoke test proves the loop).
