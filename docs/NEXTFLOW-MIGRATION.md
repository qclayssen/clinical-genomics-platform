# Nextflow 26 / nf-core migration — issues encountered

A record of every issue hit migrating the pipeline to **Nextflow 26.04** (strict DSL parser)
and nf-core conventions, with symptom → cause → fix. Kept because "document all issues" is a
first-class deliverable and because these are the exact traps anyone upgrading an older
DSL2 pipeline will hit.

## Environment

- **Nextflow 26.04.6**, **Java 26** (Temurin/openjdk; the macOS `/usr/bin/java` stub is *not*
  sufficient — Nextflow needs a real JDK 17+).
- Verified with `nextflow run main.nf -profile test -stub` → `[SUCCESS] completed=9`.

## Strict-DSL parser issues (Nextflow 25+/26)

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | `Unexpected input: '('` on `def check_max(obj, type)` in `nextflow.config` | The strict config parser disallows arbitrary function definitions in config | Removed `check_max()`; use `process.resourceLimits = [...]` (modern nf-core idiom) with retry-scaling closures `{ 2 * task.attempt }` that are auto-clamped |
| 2 | `Statements cannot be mixed with script declarations` at top-level `def provenance = [...]` | Strict DSL forbids statements outside a workflow/process/function | Moved the provenance map inside `workflow {}` |
| 3 | Same error at `workflow.onComplete { ... }` | Strict-DSL handler placement | Removed the cosmetic completion log; the real artifacts (timeline/report/trace/dag) still land in `results/provenance/` |
| 4 | `No such variable: meta` at `publishDir "…${meta.id}…"` | A GString directive referencing an input var is evaluated before inputs bind | Converted every `publishDir "…"` to a closure `publishDir { "…" }`; then (nf-core) moved publishDir out of modules entirely into `conf/modules.config` |
| 5 | `Trace file already exists` on re-run | Report files default to no-overwrite | Added `overwrite = true` to timeline/report/trace/dag |
| 6 | Type mismatch feeding `resourceLimits` | `max_memory = '16.GB'` was a quoted String | Unquoted memory/time literals (`16.GB`, `8.h`) so they carry proper types |

## nf-core convention issues

| # | Symptom / gap | Notes |
|---|---|---|
| 7 | publishDir hardcoded in modules | Moved to `conf/modules.config` via `withName` (nf-core pattern) so modules stay portable |
| 8 | No `versions.yml` emission | Added `path "versions.yml", emit: versions` (+ matching `stub:`) to every process |
| 9 | **Versions collation incomplete** | Fragments are emitted and mixed, but collation into one document is simplified in `main.nf` — a documented **loose end** (tracked in the roadmap, task #8) |
| 10 | No `nextflow_schema.json` initially | Added a params schema (`nextflow_schema.json`) |
| 11 | CI ran `nextflow config`, not `nf-core lint` | README/CLAUDE.md described CI as "nf-core lint"; the `.nf-core.yml` waivers are convention-only until a real lint step is wired — **doc/CI mismatch to reconcile** |

## Module output quirks (documented, by design)

- **BWAMEM2_ALIGN** publishes only its `.log` (`pattern: '*.log'`) — the sorted BAM is
  superseded by the MarkDuplicates BAM, so it deliberately doesn't reach `results/`.
- **DB_INGEST** has no `publishDir` — its real effect is the database write; `ingest.log` stays
  in the work dir.
- The `results/` tree is **per-sample nested** (`results/<sample>/qc|align|variants|…`), with only
  `multiqc/` and `provenance/` at the top level.

## Benign warnings (no action needed)

- `Task runtime metrics are not reported when using macOS without a container engine` — expected
  for a local, non-Docker stub run.
- `file() … matched a collection of files — use files() instead` — from the reference-index glob;
  harmless in stub mode, noted for a future tidy.

## Process / follow-ups

- The modernization was split across agents; one agent hit a **session limit mid-task**, so its
  work was committed but the **versions collation** and a clean **`nf-core lint`** pass were left
  as follow-ups (roadmap task #8). `nf-test` tests are not yet written (roadmap task #3).
