"""Tests for the post-run triage agent (ADR-0021).

No network, no GPU — triage() is a pure function and run() only calls the
dependency-free render_offline() path.
"""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ai-report"))

from triage_agent import FLAGGED, QUEUED, run, triage  # noqa: E402

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "HG002_chr20.metrics.json"


@pytest.fixture
def metrics() -> dict:
    with open(_FIXTURE) as fh:
        return json.load(fh)


def test_passing_metrics_are_queued(metrics: dict):
    decision = triage(metrics)
    assert decision.action == QUEUED
    assert decision.snp_f1 == pytest.approx(0.9978)


def test_below_threshold_is_flagged(metrics: dict):
    low = copy.deepcopy(metrics)
    low["validation"]["snp"]["f1"] = 0.95
    low["validation_pass"] = False
    decision = triage(low)
    assert decision.action == FLAGGED
    assert "below acceptance threshold" in decision.reason


def test_missing_f1_is_flagged(metrics: dict):
    missing = copy.deepcopy(metrics)
    del missing["validation"]["snp"]["f1"]
    decision = triage(missing)
    assert decision.action == FLAGGED
    assert decision.snp_f1 is None


def test_run_drafts_report_when_queued(metrics: dict):
    decision, report = run(metrics)
    assert decision.action == QUEUED
    assert report is not None
    assert "AI-DRAFTED" in report


def test_run_does_not_draft_when_flagged(metrics: dict):
    low = copy.deepcopy(metrics)
    low["validation"]["snp"]["f1"] = 0.5
    low["validation_pass"] = False
    decision, report = run(low)
    assert decision.action == FLAGGED
    assert report is None
