# ADR-0035 — Opt-in local MLflow tracking; the registered version is the adapter's provenance reference

**Status:** Accepted · **Date:** 2026-09-24 · **Relates to:** [ADR-0007](0007-qlora-small-open-model.md), [ADR-0008](0008-guardrails-human-in-the-loop.md)

## Context

The pipeline's results carry a provenance stamp (git commit, versions, checksums), but the
report-drafter's LoRA adapter did not. A saved `checkpoints/` directory says nothing about which
dataset, base model, hyperparameters or library versions produced it, and two runs overwrite each
other. Roadmap item AI-3 asks for experiment tracking and a model registry so an adapter can be
traced back to exactly how it was trained.

Constraints: the repo must stay runnable offline with no server and no cloud account; CI
(`pipeline-ci.yml` runs `train_smoke.py`) and the default commands must not change behaviour or
gain a dependency.

## Decision

1. **MLflow, opt-in.** `train_smoke.py` and `train_lora.py` take a `--mlflow` flag (the single
   switch — no env-var toggle). Without it, or when `mlflow` is not installed, tracking is a
   no-op (the latter prints a warning and training continues). Shared logic lives in
   `ai-report/tracking.py`, which imports nothing heavy at module load.
2. **Local store only.** Default backend is SQLite at `ai-report/mlruns/mlflow.db` with artifacts
   in `ai-report/mlruns/artifacts/` (gitignored). SQLite rather than the plain file store because
   recent MLflow releases default to a database backend and steer registry use towards it
   (verified with MLflow 3.16.1). The
   standard `MLFLOW_TRACKING_URI` variable can point it elsewhere.
3. **What a run records.** Hyperparameters (incl. LoRA r/alpha/dropout/targets, quantization);
   the loss curve from the Trainer's `log_history` plus final `train_loss`; tags for git commit
   (suffixed `-dirty` for uncommitted changes), dataset SHA-256, base model id, and
   torch/transformers/peft/datasets/trl/mlflow versions; the adapter directory as an artifact plus
   an `adapter_sha256` over its files.
4. **Registry version = provenance reference.** Every tracked run registers its adapter as a new
   version of `cgp-report-drafter-adapter` (via `MlflowClient.create_model_version` on the run's
   `adapter/` artifact — the adapter is a plain peft directory, not an MLflow-flavoured model).
   `<model name>/<version>` is the identifier to cite when stating which adapter drafted a report.

## Consequences

- An adapter trained with `--mlflow` can be traced to its data, code, base model and stack.
  Adapters trained without it have no such record — so the flag should be used for any adapter
  intended for use beyond a smoke test.
- The store is local and mutable (MLflow allows deleting runs/versions); it is **not** covered by
  the insert-only guarantees of ADR-0005/ADR-0012. It is a traceability aid, not a tamper-evident
  record.
- The registered version is not yet threaded into `infer.py`'s output or `metrics.json`; a report
  does not currently state which adapter version drafted it. Doing so is follow-up work.
- `mlflow` is not added to `requirements.txt` / the lock file, so CI and `pip-audit` are unchanged.

## Alternatives considered

- **Weights & Biases / hosted MLflow** — needs an account/network; rejected for an offline repo.
- **A JSON sidecar next to the adapter** — cheap, but no loss-curve UI, no run comparison, and no
  registry/versioning; would re-invent a subset of MLflow.
- **Always-on tracking** — would add a heavy dependency to CI and the default path; rejected.
