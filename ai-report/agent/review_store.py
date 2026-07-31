"""Insert-only store for human reviewer sign-off on AI-drafted interpretations.

Every AI-drafted variant interpretation carries a mandatory guardrail banner
(see report.py) telling the reader a clinician must review it — but until now
nothing captured that the review actually happened. This module closes that
gap: a reviewer's approve/reject decision is written once and never mutated,
mirroring the insert-only discipline the rest of the platform uses for runs,
qc_metrics, and audit_log (db/schema.sql). See ADR-0019.

Backed by SQLite so the demo stays zero-infrastructure (no Postgres required,
consistent with demo/data_loader.py). The schema mirrors the production
Postgres `review_decisions` table added in db/schema.sql, so the same model
holds whether the reviewer is looking at the Streamlit demo or the deployed
platform.

Deliberately exposes no update/delete method: a changed mind is a new row,
never an edit to the old one.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

VALID_DECISIONS = ("approved", "rejected")

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "demo" / ".local" / "review_decisions.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_decisions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         TEXT NOT NULL,
    variant_key    TEXT NOT NULL,
    classification TEXT NOT NULL,
    decision       TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    reviewer       TEXT NOT NULL,
    comment        TEXT NOT NULL DEFAULT '',
    decided_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_review_variant ON review_decisions(variant_key);
CREATE INDEX IF NOT EXISTS idx_review_run ON review_decisions(run_id);
"""


@dataclass(frozen=True)
class ReviewDecision:
    id: int
    run_id: str
    variant_key: str
    classification: str
    decision: str
    reviewer: str
    comment: str
    decided_at: str


class ReviewStore:
    """Append-only reviewer decision log. No update or delete is exposed."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # A fresh sqlite3.connect(":memory:") opens a *new* empty database each
        # time, so an in-memory store must reuse one connection for its whole
        # lifetime — otherwise every call after __init__ sees a missing table.
        # File-backed stores could reconnect per call, but reusing one
        # connection is simpler and correct for both cases at this scale.
        self._conn = self._connect()
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def record_decision(
        self,
        *,
        run_id: str,
        variant_key: str,
        classification: str,
        decision: str,
        reviewer: str,
        comment: str = "",
    ) -> int:
        """Insert one reviewer decision. Returns the new row id.

        Raises ValueError for an unrecognised decision or a blank reviewer —
        a decision must always be attributable to a named person.
        """
        if decision not in VALID_DECISIONS:
            raise ValueError(f"decision must be one of {VALID_DECISIONS}, got {decision!r}")
        if not reviewer or not reviewer.strip():
            raise ValueError("reviewer name is required")

        decided_at = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO review_decisions
                (run_id, variant_key, classification, decision, reviewer, comment, decided_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, variant_key, classification, decision, reviewer.strip(), comment, decided_at),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_decisions(
        self, *, variant_key: str | None = None, run_id: str | None = None
    ) -> list[ReviewDecision]:
        """Return decisions newest-first, optionally filtered by variant or run."""
        query = "SELECT * FROM review_decisions"
        clauses, params = [], []
        if variant_key is not None:
            clauses.append("variant_key = ?")
            params.append(variant_key)
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY decided_at DESC"

        rows = self._conn.execute(query, params).fetchall()
        return [ReviewDecision(**dict(row)) for row in rows]


def variant_key(chrom: str, pos: int, ref: str, alt: str) -> str:
    """Canonical identifier used to key a review decision to a variant."""
    return f"{chrom}:{pos}:{ref}>{alt}"
