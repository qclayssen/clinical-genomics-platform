"""Unit tests for ai-report/tracking.py (optional MLflow experiment tracking, AI-3).

These run without mlflow, torch or transformers installed: the no-op path is tested
directly, the mlflow path is tested against a fake ``mlflow`` module, and one
end-to-end test against a real local store runs only when mlflow is importable.
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

AI_REPORT = Path(__file__).resolve().parent.parent / "ai-report"
sys.path.insert(0, str(AI_REPORT))

import tracking  # noqa: E402


# --------------------------------------------------------------------------- helpers
def test_sha256_file_matches_hashlib(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_bytes(b'{"input": "x", "output": "y"}\n')
    assert tracking.sha256_file(str(p)) == hashlib.sha256(p.read_bytes()).hexdigest()


def test_sha256_dir_is_deterministic_and_content_sensitive(tmp_path):
    d = tmp_path / "adapter"
    (d / "sub").mkdir(parents=True)
    (d / "adapter_config.json").write_text("{}")
    (d / "sub" / "w.bin").write_bytes(b"\x00\x01")
    first = tracking.sha256_dir(str(d))
    assert first == tracking.sha256_dir(str(d))
    (d / "sub" / "w.bin").write_bytes(b"\x00\x02")
    assert tracking.sha256_dir(str(d)) != first


def test_sha256_dir_sensitive_to_file_names(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "x").write_text("same")
    (b / "y").write_text("same")
    assert tracking.sha256_dir(str(a)) != tracking.sha256_dir(str(b))


def test_git_commit_in_repo_is_a_sha():
    sha = tracking.git_commit()
    assert sha == "unknown" or len(sha.removesuffix("-dirty")) == 40


def test_git_commit_outside_repo_is_unknown(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise subprocess.CalledProcessError(128, "git")
    monkeypatch.setattr(tracking.subprocess, "run", boom)
    assert tracking.git_commit(str(tmp_path)) == "unknown"


def test_package_versions_marks_missing():
    v = tracking.package_versions(["pytest", "definitely-not-a-real-pkg-xyz"])
    assert v["pytest"] not in ("", "not-installed")
    assert v["definitely-not-a-real-pkg-xyz"] == "not-installed"


def test_build_tags_has_required_provenance(tmp_path):
    data = tmp_path / "pairs.jsonl"
    data.write_text('{"input": "{}", "output": "x"}\n')
    tags = tracking.build_tags("sshleifer/tiny-gpt2", str(data), "ai-report/train_smoke.py")
    assert tags["base_model"] == "sshleifer/tiny-gpt2"
    assert tags["dataset_sha256"] == hashlib.sha256(data.read_bytes()).hexdigest()
    assert tags["git_commit"]
    for pkg in ("torch", "transformers", "peft"):
        assert f"version.{pkg}" in tags
    assert all(isinstance(v, str) for v in tags.values())


def test_loss_curve_extracts_numeric_step_metrics():
    history = [
        {"loss": 10.8, "grad_norm": 0.003, "learning_rate": 4e-4, "epoch": 0.4, "step": 5},
        {"loss": 10.7, "learning_rate": 2e-4, "epoch": 0.8, "step": 10},
        {"train_loss": 10.75, "train_runtime": 1.0, "epoch": 0.8, "step": 10,
         "note": "ignored-string", "flag": True},
        {"no_step": 1.0},
    ]
    curve = tracking.loss_curve(history)
    assert curve[0] == (5, {"loss": 10.8, "grad_norm": 0.003, "learning_rate": 4e-4})
    assert curve[1] == (10, {"loss": 10.7, "learning_rate": 2e-4})
    assert curve[2] == (10, {"train_loss": 10.75, "train_runtime": 1.0})
    assert len(curve) == 3


def test_default_tracking_uri_respects_env(monkeypatch, tmp_path):
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    uri = tracking.default_tracking_uri(str(tmp_path))
    assert uri.startswith("sqlite:///") and uri.endswith("mlflow.db")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://example.invalid:5000")
    assert tracking.default_tracking_uri(str(tmp_path)) == "http://example.invalid:5000"


def test_cli_flag_defaults_off():
    ap = argparse.ArgumentParser()
    tracking.add_cli_args(ap)
    args = ap.parse_args([])
    assert args.mlflow is False
    assert args.mlflow_model_name == tracking.DEFAULT_REGISTERED_MODEL
    assert ap.parse_args(["--mlflow"]).mlflow is True


# --------------------------------------------------------------------------- no-op path
def test_disabled_returns_null_tracker(tmp_path):
    t = tracking.start_tracking(False, base_model="m", data_path=str(tmp_path / "missing"),
                                script="s")
    assert isinstance(t, tracking.NullTracker) and not t.enabled
    with t:
        t.log_params({"a": 1})
        t.log_metrics({"loss": 1.0}, step=1)
        t.log_history([{"loss": 1.0, "step": 1}])
        assert t.log_adapter(str(tmp_path)) is None
    assert t.run_id is None


def test_enabled_without_mlflow_warns_and_noops(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tracking, "mlflow_available", lambda: False)
    t = tracking.start_tracking(True, base_model="m", data_path=str(tmp_path / "missing"),
                                script="s", store_dir=str(tmp_path / "mlruns"))
    assert type(t) is tracking.NullTracker
    assert "mlflow is not installed" in capsys.readouterr().err
    assert not (tmp_path / "mlruns").exists()


def test_mlflow_available_false_when_import_fails(monkeypatch):
    monkeypatch.setitem(sys.modules, "mlflow", None)  # makes `import mlflow` raise
    assert tracking.mlflow_available() is False


# --------------------------------------------------------------------------- fake mlflow
class _FakeClient:
    def __init__(self, calls, **kw):
        self.calls = calls

    def create_registered_model(self, name, description=None):
        if name in self.calls["registered"]:
            raise RuntimeError("RESOURCE_ALREADY_EXISTS: already exists")
        self.calls["registered"].add(name)

    def create_model_version(self, name, source, run_id, tags=None, description=None):
        self.calls["versions"].append((name, source, run_id, tags))
        return types.SimpleNamespace(version=len(self.calls["versions"]))


def _fake_mlflow():
    calls = {"params": {}, "metrics": [], "tags": {}, "artifacts": [], "end": None,
             "registered": set(), "versions": [], "experiments": {}}
    m = types.SimpleNamespace()
    m.set_tracking_uri = lambda uri: calls.__setitem__("uri", uri)
    m.set_registry_uri = lambda uri: None
    m.get_experiment_by_name = lambda n: calls["experiments"].get(n)
    m.create_experiment = lambda n, artifact_location=None: calls["experiments"].__setitem__(
        n, artifact_location)
    m.set_experiment = lambda n: None
    m.start_run = lambda run_name=None, tags=None: (
        calls["tags"].update(tags or {}),
        types.SimpleNamespace(info=types.SimpleNamespace(run_id="run123")))[1]
    m.end_run = lambda status="FINISHED": calls.__setitem__("end", status)
    m.log_params = lambda p: calls["params"].update(p)
    m.log_metrics = lambda d, step=None: calls["metrics"].append((step, d))
    m.set_tag = lambda k, v: calls["tags"].__setitem__(k, v)
    # Record what was actually uploaded (the dir may be a temp staging copy).
    m.log_artifacts = lambda d, artifact_path=None: calls["artifacts"].append(
        (sorted(str(p.relative_to(d)) for p in Path(d).rglob("*") if p.is_file()), artifact_path))
    m.get_artifact_uri = lambda p: f"file:///store/run123/artifacts/{p}"
    m.tracking = types.SimpleNamespace(MlflowClient=lambda **kw: _FakeClient(calls, **kw))
    return m, calls


def _tracker(m, tags=None):
    return tracking.MlflowTracker(
        m, experiment="exp", run_name=None,
        tags=tags or {"git_commit": "abc", "dataset_sha256": "d" * 64, "base_model": "tiny"},
        registered_model="cgp-test-adapter", tracking_uri="sqlite:///x.db",
    )


def test_mlflow_tracker_logs_run_and_registers_adapter(tmp_path):
    m, calls = _fake_mlflow()
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "adapter_model.safetensors").write_bytes(b"weights")
    (adapter / "checkpoint-10").mkdir()
    (adapter / "checkpoint-10" / "optimizer.pt").write_bytes(b"optimizer state")
    with _tracker(m) as t:
        assert t.run_id == "run123"
        t.log_params({"learning_rate": 5e-4, "unused": None})
        t.log_history([{"loss": 3.0, "step": 5, "epoch": 0.5}, {"loss": 2.0, "step": 10}])
        version = t.log_adapter(str(adapter))
    assert calls["params"] == {"learning_rate": 5e-4}
    assert calls["metrics"] == [(5, {"loss": 3.0}), (10, {"loss": 2.0})]
    # Trainer checkpoints are not part of the registered adapter.
    assert calls["artifacts"] == [(["adapter_model.safetensors"], "adapter")]
    assert version == "1"
    name, source, run_id, vtags = calls["versions"][0]
    assert (name, run_id) == ("cgp-test-adapter", "run123")
    assert source.endswith("/adapter")
    assert vtags["adapter_sha256"] == tracking.sha256_dir(str(adapter), exclude=tracking.ADAPTER_EXCLUDE)
    assert vtags["git_commit"] == "abc" and vtags["base_model"] == "tiny"
    assert calls["tags"]["registered_model"] == "cgp-test-adapter/1"
    assert calls["end"] == "FINISHED"


def test_mlflow_tracker_second_registration_bumps_version(tmp_path):
    m, calls = _fake_mlflow()
    (tmp_path / "f").write_text("x")
    with _tracker(m) as t:
        assert t.log_adapter(str(tmp_path)) == "1"
    with _tracker(m) as t:
        assert t.log_adapter(str(tmp_path)) == "2"


def test_mlflow_tracker_marks_run_failed_on_exception():
    m, calls = _fake_mlflow()
    with pytest.raises(ValueError):
        with _tracker(m):
            raise ValueError("training blew up")
    assert calls["end"] == "FAILED"


# --------------------------------------------------------------------------- real mlflow
def test_real_local_store_roundtrip(tmp_path, monkeypatch):
    mlflow = pytest.importorskip("mlflow")
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    data = tmp_path / "pairs.jsonl"
    data.write_text('{"input": "{}", "output": "x"}\n')
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "adapter_config.json").write_text("{}")
    store = tmp_path / "mlruns"
    t = tracking.start_tracking(True, base_model="tiny", data_path=str(data), script="s",
                                experiment="t-exp", registered_model="t-adapter",
                                store_dir=str(store))
    with t:
        t.log_params({"lr": 1e-3})
        t.log_history([{"loss": 1.5, "step": 1}])
        version = t.log_adapter(str(adapter))
    assert version == "1"
    client = mlflow.tracking.MlflowClient(tracking_uri=t.tracking_uri,
                                          registry_uri=t.tracking_uri)
    run = client.get_run(t.run_id)
    assert run.data.tags["dataset_sha256"] == tracking.sha256_file(str(data))
    assert run.data.params["lr"] == "0.001"
    mv = client.get_model_version("t-adapter", "1")
    assert mv.run_id == t.run_id


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def test_git_commit_dirty_suffix_includes_untracked(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    _git(tmp_path, "init", "-q")
    (tmp_path / "a.py").write_text("x = 1\n")
    _git(tmp_path, "add", "a.py")
    _git(tmp_path, "commit", "-qm", "init")
    clean = tracking.git_commit(str(tmp_path))
    assert len(clean) == 40 and not clean.endswith("-dirty")
    (tmp_path / "new_helper.py").write_text("y = 2\n")  # untracked source file
    assert tracking.git_commit(str(tmp_path)) == f"{clean}-dirty"


def test_sha256_dir_excludes_trainer_checkpoints(tmp_path):
    (tmp_path / "adapter_model.safetensors").write_text("weights")
    before = tracking.sha256_dir(str(tmp_path), exclude=tracking.ADAPTER_EXCLUDE)
    ck = tmp_path / "checkpoint-10"
    ck.mkdir()
    (ck / "optimizer.pt").write_text("big optimizer state")
    assert tracking.sha256_dir(str(tmp_path), exclude=tracking.ADAPTER_EXCLUDE) == before
    assert tracking.sha256_dir(str(tmp_path)) != before
