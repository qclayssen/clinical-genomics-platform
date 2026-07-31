#!/usr/bin/env python3
"""Post-run triage agent: decide re-validate vs. draft-and-queue-for-review.

Distinct from lambdas/healer/handler.py (ADR-0018), which diagnoses pipeline
*execution* failures mid-run (retry/quarantine decisions on Batch/Fargate).
This agent runs *after* a run has completed and a metrics.json exists: it
checks whether the result met the platform's acceptance criterion and either
flags it for re-validation or drafts a guardrailed summary and queues it for
human review.

Deliberately a plain script, not a new agent framework — one perceive/decide/
act/log pass over a single metrics.json:
  perceive -> load_metrics()
  decide   -> triage()          (SNP F1 >= 0.99, matching README/VALIDATION.md)
  act      -> run()             (draft via infer.render_offline, or flag)
  log      -> every decision is printed as one structured JSON line, so this
              is trivially pipeable into a real audit trail. Writing to
              db/schema.sql's audit_log table is a natural next step but is
              intentionally left as a TODO rather than added here — this
              script stays dependency-free (no psycopg2), matching
              infer.py's --offline path.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from infer import enforce_guardrails, render_offline

logger = logging.getLogger(__name__)

# Matches the SNV acceptance criterion documented in CLAUDE.md / docs/VALIDATION.md.
F1_ACCEPTANCE_THRESHOLD = 0.99

FLAGGED = "flagged_for_revalidation"
QUEUED = "drafted_and_queued"


@dataclass
class TriageDecision:
    run_id: str
    sample: str
    action: str  # FLAGGED or QUEUED
    snp_f1: float | None
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def load_metrics(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


def triage(m: dict) -> TriageDecision:
    """Perceive + decide: no side effects, pure function of the metrics dict."""
    prov = m.get("provenance", {})
    run_id = prov.get("run_id", "unknown")
    sample = m.get("sample", "unknown")
    snp = m.get("validation", {}).get("snp", {})
    f1 = snp.get("f1")
    passed = m.get("validation_pass", False)

    if f1 is None:
        return TriageDecision(run_id, sample, FLAGGED, None, "SNP F1 missing from metrics")
    if not passed or f1 < F1_ACCEPTANCE_THRESHOLD:
        reason = (
            f"SNP F1 {f1:.4f} below acceptance threshold {F1_ACCEPTANCE_THRESHOLD} "
            f"(validation_pass={passed})"
        )
        return TriageDecision(run_id, sample, FLAGGED, f1, reason)

    return TriageDecision(
        run_id, sample, QUEUED, f1,
        f"SNP F1 {f1:.4f} meets acceptance threshold {F1_ACCEPTANCE_THRESHOLD}",
    )


def run(m: dict) -> tuple[TriageDecision, str | None]:
    """Act: draft a guardrailed report when queued, otherwise no report.

    Returns (decision, report_or_none). Logging is left to the caller so the
    CLI and any future caller (e.g. a batch triage over many runs) can choose
    their own log sink.
    """
    decision = triage(m)
    report = None
    if decision.action == QUEUED:
        report = enforce_guardrails(render_offline(m), m)
    return decision, report


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--out", default=None, help="write the drafted report here, if queued")
    args = ap.parse_args()

    m = load_metrics(args.metrics)
    decision, report = run(m)

    logger.info("triage_decision %s", json.dumps(decision.to_dict()))

    if report is not None:
        if args.out:
            Path(args.out).write_text(report + "\n")
        print(report)
    else:
        print(json.dumps(decision.to_dict(), indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
