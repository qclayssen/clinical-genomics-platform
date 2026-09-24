"""Optional MLflow experiment tracking + model registry for the report-drafter adapter.

Shared by ``train_smoke.py`` and ``train_lora.py``. Tracking is **opt-in** via the
``--mlflow`` flag on those scripts; without it — or when ``mlflow`` is not installed —
every call here is a silent (or warned) no-op, so the existing commands and CI behave
exactly as before.

What a tracked run records:

* **params**   — the training hyperparameters (lr, epochs, max steps, LoRA r/alpha/…).
* **metrics**  — the loss curve (``loss`` per logged step, from the Trainer's
  ``log_history``) plus the final ``train_loss``.
* **tags**     — provenance: git commit SHA, dataset SHA-256, base model id, and the
  torch / transformers / peft / datasets versions, plus the adapter's SHA-256.
* **artifact** — the saved LoRA adapter directory, registered as a new version of a
  model in the local MLflow model registry. That registered version is the provenance
  reference for the adapter (see MODEL_CARD.md).

Storage is local only — no tracking server. The default backend is a SQLite file under
``ai-report/mlruns/`` (gitignored), with artifacts alongside it. Set the standard
``MLFLOW_TRACKING_URI`` environment variable to point somewhere else.

This module imports nothing heavy at import time (no mlflow, torch or transformers), so
it is safe to import from tests and from ``--help``.
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from importlib import metadata
from typing import Any, Iterable, Mapping, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

#: Local store (gitignored). SQLite backs runs + the model registry; artifacts sit next to it.
DEFAULT_STORE_DIR = os.path.join(HERE, "mlruns")
DEFAULT_EXPERIMENT = "cgp-report-drafter"
DEFAULT_REGISTERED_MODEL = "cgp-report-drafter-adapter"

#: Library versions recorded as tags (missing packages are recorded as "not-installed").
TRACKED_PACKAGES = ("torch", "transformers", "peft", "datasets", "trl", "mlflow")


# --------------------------------------------------------------------------- helpers
def mlflow_available() -> bool:
    """True if ``mlflow`` can be imported."""
    try:
        import mlflow  # noqa: F401
    except ImportError:
        return False
    return True


def default_tracking_uri(store_dir: str = DEFAULT_STORE_DIR) -> str:
    """``MLFLOW_TRACKING_URI`` if set, else a SQLite DB inside ``store_dir``."""
    env = os.environ.get("MLFLOW_TRACKING_URI")
    if env:
        return env
    return "sqlite:///" + os.path.join(os.path.abspath(store_dir), "mlflow.db")


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    """Hex SHA-256 of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


# Trainer checkpoints (``checkpoint-N/``, incl. optimizer state) are written
# into the same output dir as the adapter; they are not part of the adapter.
ADAPTER_EXCLUDE = ("checkpoint-*",)


def sha256_dir(path: str, exclude: Iterable[str] = ()) -> str:
    """Deterministic SHA-256 over a directory: sorted relative paths + file contents.

    Used for the adapter directory, so the tag changes iff any saved file changes.
    Top-level entries matching an ``exclude`` glob are skipped.
    """
    h = hashlib.sha256()
    for root, dirs, files in os.walk(path):
        if root == path:
            dirs[:] = [d for d in dirs if not any(fnmatch.fnmatch(d, p) for p in exclude)]
            files = [f for f in files if not any(fnmatch.fnmatch(f, p) for p in exclude)]
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, path).replace(os.sep, "/")
            h.update(rel.encode("utf-8") + b"\0")
            h.update(sha256_file(full).encode("ascii") + b"\n")
    return h.hexdigest()


def git_commit(cwd: str = REPO_ROOT) -> str:
    """Current git commit SHA, suffixed ``-dirty`` if the tree has changes; ``unknown`` if no git."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True,
            check=True, timeout=10,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=cwd,
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return f"{sha}-dirty" if dirty else sha


def package_versions(packages: Iterable[str] = TRACKED_PACKAGES) -> dict[str, str]:
    """Installed version of each package, or ``not-installed``."""
    out: dict[str, str] = {}
    for pkg in packages:
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = "not-installed"
    return out


def build_tags(base_model: str, data_path: str, script: str) -> dict[str, str]:
    """Provenance tags for a training run."""
    tags = {
        "git_commit": git_commit(),
        "dataset_path": os.path.relpath(os.path.abspath(data_path), REPO_ROOT),
        "dataset_sha256": sha256_file(data_path),
        "base_model": base_model,
        "script": script,
        "python_version": sys.version.split()[0],
    }
    for pkg, ver in package_versions().items():
        tags[f"version.{pkg}"] = ver
    return tags


def loss_curve(log_history: Iterable[Mapping[str, Any]]) -> list[tuple[int, dict[str, float]]]:
    """Extract ``(step, {metric: value})`` pairs from a HF ``Trainer.state.log_history``.

    Per-step entries carry ``loss`` (and usually ``learning_rate``/``grad_norm``); the
    final summary entry carries ``train_loss`` etc. Only numeric values are kept.
    """
    points: list[tuple[int, dict[str, float]]] = []
    for entry in log_history:
        step = entry.get("step")
        if step is None:
            continue
        vals = {
            k: float(v) for k, v in entry.items()
            if k not in ("step", "epoch") and isinstance(v, (int, float))
            and not isinstance(v, bool)
        }
        if vals:
            points.append((int(step), vals))
    return points


# --------------------------------------------------------------------------- trackers
class NullTracker:
    """No-op tracker used when tracking is off or mlflow is unavailable."""

    enabled = False
    run_id: Optional[str] = None

    def __enter__(self) -> "NullTracker":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def log_params(self, params: Mapping[str, Any]) -> None:
        pass

    def log_metrics(self, metrics: Mapping[str, float], step: Optional[int] = None) -> None:
        pass

    def log_history(self, log_history: Iterable[Mapping[str, Any]]) -> None:
        pass

    def log_adapter(self, adapter_dir: str) -> Optional[str]:
        return None


class MlflowTracker(NullTracker):
    """Thin wrapper over the mlflow fluent API for one training run."""

    enabled = True

    def __init__(
        self,
        mlflow_module: Any,
        experiment: str,
        run_name: Optional[str],
        tags: Mapping[str, str],
        registered_model: str,
        tracking_uri: str,
        artifact_location: Optional[str] = None,
    ) -> None:
        self._mlflow = mlflow_module
        self.experiment = experiment
        self.run_name = run_name
        self.tags = dict(tags)
        self.registered_model = registered_model
        self.tracking_uri = tracking_uri
        self.artifact_location = artifact_location
        self.run_id = None
        self.model_version: Optional[str] = None

    def __enter__(self) -> "MlflowTracker":
        mlflow = self._mlflow
        mlflow.set_tracking_uri(self.tracking_uri)
        mlflow.set_registry_uri(self.tracking_uri)
        if mlflow.get_experiment_by_name(self.experiment) is None:
            mlflow.create_experiment(self.experiment, artifact_location=self.artifact_location)
        mlflow.set_experiment(self.experiment)
        run = mlflow.start_run(run_name=self.run_name, tags=self.tags)
        self.run_id = run.info.run_id
        print(f"[mlflow] tracking run {self.run_id} "
              f"(experiment '{self.experiment}', store {self.tracking_uri})")
        return self

    def __exit__(self, exc_type: Any, *exc: Any) -> None:
        self._mlflow.end_run(status="FAILED" if exc_type else "FINISHED")

    def log_params(self, params: Mapping[str, Any]) -> None:
        self._mlflow.log_params({k: v for k, v in params.items() if v is not None})

    def log_metrics(self, metrics: Mapping[str, float], step: Optional[int] = None) -> None:
        self._mlflow.log_metrics(dict(metrics), step=step)

    def log_history(self, log_history: Iterable[Mapping[str, Any]]) -> None:
        for step, vals in loss_curve(log_history):
            self._mlflow.log_metrics(vals, step=step)

    def log_adapter(self, adapter_dir: str) -> Optional[str]:
        """Log the adapter dir as an artifact and register it as a new model version.

        Registration uses ``MlflowClient.create_model_version`` against the run's
        ``adapter/`` artifact path — the adapter is a plain peft directory, not an
        MLflow-flavoured model, so this avoids needing a model flavour.
        Returns the new registered version number (as a string).
        """
        mlflow = self._mlflow
        digest = sha256_dir(adapter_dir, exclude=ADAPTER_EXCLUDE)
        mlflow.set_tag("adapter_sha256", digest)
        with tempfile.TemporaryDirectory() as tmp:
            staged = os.path.join(tmp, "adapter")
            shutil.copytree(adapter_dir, staged,
                            ignore=shutil.ignore_patterns(*ADAPTER_EXCLUDE))
            mlflow.log_artifacts(staged, artifact_path="adapter")

        client = mlflow.tracking.MlflowClient(
            tracking_uri=self.tracking_uri, registry_uri=self.tracking_uri)
        try:
            client.create_registered_model(
                self.registered_model,
                description="LoRA adapter for the CGP report drafter (see ai-report/MODEL_CARD.md).",
            )
        except Exception as exc:  # already exists -> fine
            if "already exists" not in str(exc).lower() and "RESOURCE_ALREADY_EXISTS" not in str(exc):
                raise
        source = mlflow.get_artifact_uri("adapter")
        mv = client.create_model_version(
            name=self.registered_model,
            source=source,
            run_id=self.run_id,
            tags={
                "git_commit": self.tags.get("git_commit", "unknown"),
                "dataset_sha256": self.tags.get("dataset_sha256", "unknown"),
                "base_model": self.tags.get("base_model", "unknown"),
                "adapter_sha256": digest,
            },
            description="Registered by ai-report training script; human review still required for all output.",
        )
        self.model_version = str(mv.version)
        mlflow.set_tag("registered_model", f"{self.registered_model}/{self.model_version}")
        print(f"[mlflow] registered adapter as model '{self.registered_model}' "
              f"version {self.model_version} (run {self.run_id})")
        return self.model_version


def start_tracking(
    enabled: bool,
    *,
    base_model: str,
    data_path: str,
    script: str,
    experiment: str = DEFAULT_EXPERIMENT,
    run_name: Optional[str] = None,
    registered_model: str = DEFAULT_REGISTERED_MODEL,
    store_dir: str = DEFAULT_STORE_DIR,
) -> NullTracker:
    """Return a tracker context manager.

    ``enabled=False``            -> ``NullTracker`` (silent no-op; the default path).
    ``enabled=True``, no mlflow  -> ``NullTracker`` with a warning on stderr; training
                                    still runs, it just isn't tracked.
    ``enabled=True``, mlflow ok  -> ``MlflowTracker`` writing to the local store.
    """
    if not enabled:
        return NullTracker()
    if not mlflow_available():
        print("[mlflow] WARNING: --mlflow given but mlflow is not installed "
              "(pip install mlflow); continuing WITHOUT tracking.", file=sys.stderr)
        return NullTracker()
    import mlflow

    tracking_uri = default_tracking_uri(store_dir)
    artifact_location = None
    if tracking_uri.startswith("sqlite:///") and "MLFLOW_TRACKING_URI" not in os.environ:
        os.makedirs(store_dir, exist_ok=True)
        artifact_location = "file://" + os.path.join(os.path.abspath(store_dir), "artifacts")
    return MlflowTracker(
        mlflow,
        experiment=experiment,
        run_name=run_name,
        tags=build_tags(base_model, data_path, script),
        registered_model=registered_model,
        tracking_uri=tracking_uri,
        artifact_location=artifact_location,
    )


def add_cli_args(ap: Any) -> None:
    """Add the shared ``--mlflow`` flags to an argparse parser."""
    g = ap.add_argument_group("experiment tracking (optional, needs `pip install mlflow`)")
    g.add_argument("--mlflow", action="store_true",
                   help="log params/metrics/provenance tags to a local MLflow store and "
                        "register the adapter in the local model registry")
    g.add_argument("--mlflow-experiment", default=DEFAULT_EXPERIMENT)
    g.add_argument("--mlflow-model-name", default=DEFAULT_REGISTERED_MODEL,
                   help="registered-model name the adapter is versioned under")
    g.add_argument("--mlflow-run-name", default=None)
