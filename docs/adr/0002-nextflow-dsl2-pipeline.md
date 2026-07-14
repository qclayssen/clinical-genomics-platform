# ADR-0002 — Use Nextflow DSL2 (nf-core style) for the pipeline

**Status:** Accepted · **Date:** 2026-05-03

## Context

The core work is a multi-step genomics pipeline (QC → align → call → validate → export) that
must run both on a laptop and at scale on the cloud, restart cleanly on failure, and be
readable to reviewers who work in this field. The two roles targeted (UMCCR-style clinical
WGS, MiLaboratories) both live in the Nextflow/nf-core world.

## Decision

Implement the pipeline in **Nextflow, DSL2**, following **nf-core conventions**: one process
per module file, a `test`/`aws` profile split, container-per-process, and captured run
provenance (timeline, trace, DAG).

## Consequences

**Good**
- The same pipeline code runs unchanged locally and on AWS Batch — only the profile changes
  ([ADR-0004](0004-aws-cdk-batch-fargate.md)).
- Nextflow's resume/caching and execution reports contribute directly to the provenance and
  reproducibility story.
- Familiar structure to the target employers; low "translation cost" when reviewing.
- Modules are assay-agnostic, so an immune-repertoire path can be added later without
  rework.

**Bad / accepted limitations**
- Nextflow's Groovy-based DSL has a learning curve and its own footguns (config syntax,
  channel semantics).
- Running the full pipeline requires Nextflow + a container engine installed; only the
  dependency-free helpers and the `-stub` DAG run without them.

## Alternatives considered

- **Snakemake** — excellent and Python-native, but Nextflow is the lingua franca of the
  specific clinical-WGS teams targeted, and its AWS Batch executor is more mature.
- **A hand-rolled Python/Bash orchestrator** — rejected: reinvents scheduling, retries,
  provenance, and portability that Nextflow already provides.
- **WDL + Cromwell** — viable in genomics, but a heavier operational footprint and less
  aligned with the target employers than nf-core.
