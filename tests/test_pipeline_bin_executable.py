"""Every pipeline/bin script a module invokes by name must be executable.

Nextflow puts pipeline/bin on PATH and runs these scripts directly, so a script
committed without its executable bit fails with "bad interpreter: Permission denied" —
but only in a real run, never under -stub. qc_evaluate.py shipped that way and broke
every real run at QC_EVALUATE until the Phase 3 validation run surfaced it.
"""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "pipeline" / "bin"


def _invoked_bin_scripts():
    sources = [ROOT / "pipeline" / "main.nf", *(ROOT / "pipeline" / "modules").rglob("*.nf")]
    names = {p.name for p in BIN.iterdir() if p.is_file()}
    invoked = set()
    for src in sources:
        text = src.read_text()
        invoked |= {n for n in names if re.search(rf"(?<![\w/.]){re.escape(n)}\b", text)}
    return sorted(invoked)


def test_some_bin_scripts_are_invoked():
    assert "qc_evaluate.py" in _invoked_bin_scripts()
    assert "build_metrics.py" in _invoked_bin_scripts()


def test_invoked_bin_scripts_are_executable():
    not_executable = [n for n in _invoked_bin_scripts() if not os.access(BIN / n, os.X_OK)]
    assert not_executable == []
