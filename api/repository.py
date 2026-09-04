"""Data access layer for the API.

Two implementations of the same Protocol so routers never know which backend
they're talking to:

- FixtureRepository: reads api/data/demo_runs.json, keeps review decisions
  in-memory. Used by default — zero external setup.
- PostgresRepository: reads the tables defined in db/schema.sql. Used when
  CGP_DB_URL is set. review_decisions is insert-only, matching the DB
  trigger that forbids UPDATE/DELETE.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from typing import Protocol

from api.models import Provenance, QcMetrics, QcWarning, Run, ReviewDecision, ReviewDecisionCreate

DEMO_DATA_PATH = Path(__file__).parent / "data" / "demo_runs.json"


class RunNotFoundError(LookupError):
    def __init__(self, run_id: str):
        super().__init__(f"run '{run_id}' not found")
        self.run_id = run_id


class Repository(Protocol):
    def list_runs(
        self, sample_id: str | None, caller: str | None, validation_pass: bool | None, limit: int, offset: int
    ) -> list[Run]: ...

    def get_run(self, run_id: str) -> Run: ...

    def get_provenance(self, run_id: str) -> Provenance: ...

    def list_qc_warnings(self, run_id: str) -> list[QcWarning]: ...

    def create_review_decision(self, run_id: str, decision: ReviewDecisionCreate) -> ReviewDecision: ...


class FixtureRepository:
    def __init__(self, data_path: Path = DEMO_DATA_PATH):
        raw = json.loads(data_path.read_text())
        self._runs: dict[str, dict] = {r["provenance"]["run_id"]: r for r in raw["runs"]}
        self._review_decisions: list[ReviewDecision] = []
        self._next_id = count(1)

    def _to_run(self, record: dict) -> Run:
        prov = record["provenance"]
        return Run(
            run_id=prov["run_id"],
            sample_id=record["sample"],
            pipeline_version=prov["pipeline_version"],
            caller=prov["caller"],
            validation_pass=record["validation_pass"],
            started_at=prov.get("started_at"),
            exported_at=prov.get("exported_at"),
            qc=QcMetrics(
                percent_duplication=record["qc"].get("percent_duplication"),
                snp_precision=record["validation"]["snp"]["precision"],
                snp_recall=record["validation"]["snp"]["recall"],
                snp_f1=record["validation"]["snp"]["f1"],
                n_variants=prov.get("n_variants"),
            ),
        )

    def list_runs(
        self,
        sample_id: str | None = None,
        caller: str | None = None,
        validation_pass: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Run]:
        runs = [self._to_run(r) for r in self._runs.values()]
        if sample_id is not None:
            runs = [r for r in runs if r.sample_id == sample_id]
        if caller is not None:
            runs = [r for r in runs if r.caller == caller]
        if validation_pass is not None:
            runs = [r for r in runs if r.validation_pass == validation_pass]
        return runs[offset : offset + limit]

    def get_run(self, run_id: str) -> Run:
        record = self._runs.get(run_id)
        if record is None:
            raise RunNotFoundError(run_id)
        return self._to_run(record)

    def get_provenance(self, run_id: str) -> Provenance:
        record = self._runs.get(run_id)
        if record is None:
            raise RunNotFoundError(run_id)
        return Provenance(**record["provenance"])

    def list_qc_warnings(self, run_id: str) -> list[QcWarning]:
        record = self._runs.get(run_id)
        if record is None:
            raise RunNotFoundError(run_id)
        return [QcWarning(run_id=run_id, **w) for w in record.get("qc_warnings", [])]

    def create_review_decision(self, run_id: str, decision: ReviewDecisionCreate) -> ReviewDecision:
        if run_id not in self._runs:
            raise RunNotFoundError(run_id)
        record = ReviewDecision(
            id=next(self._next_id),
            run_id=run_id,
            decided_at=datetime.now(timezone.utc),
            **decision.model_dump(),
        )
        self._review_decisions.append(record)
        return record


class PostgresRepository:
    """Reads db/schema.sql tables directly. Requires `psycopg[binary]`."""

    def __init__(self, dsn: str):
        self._dsn = dsn

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self._dsn, row_factory=dict_row)

    def list_runs(
        self,
        sample_id: str | None = None,
        caller: str | None = None,
        validation_pass: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Run]:
        clauses, params = [], []
        if sample_id is not None:
            clauses.append("r.sample_id = %s")
            params.append(sample_id)
        if caller is not None:
            clauses.append("r.caller = %s")
            params.append(caller)
        if validation_pass is not None:
            clauses.append("r.validation_pass = %s")
            params.append(validation_pass)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT r.run_id, r.sample_id, r.pipeline_version, r.caller, r.validation_pass,
                   r.started_at, r.exported_at,
                   q.percent_duplication, q.snp_precision, q.snp_recall, q.snp_f1, q.n_variants
            FROM runs r
            LEFT JOIN LATERAL (
                SELECT * FROM qc_metrics WHERE run_pk = r.id ORDER BY recorded_at DESC LIMIT 1
            ) q ON true
            {where}
            ORDER BY r.ingested_at DESC
            LIMIT %s OFFSET %s
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(query, [*params, limit, offset])
            rows = cur.fetchall()
        return [
            Run(
                run_id=row["run_id"],
                sample_id=row["sample_id"],
                pipeline_version=row["pipeline_version"],
                caller=row["caller"],
                validation_pass=row["validation_pass"],
                started_at=row["started_at"],
                exported_at=row["exported_at"],
                qc=QcMetrics(
                    percent_duplication=row["percent_duplication"],
                    snp_precision=row["snp_precision"],
                    snp_recall=row["snp_recall"],
                    snp_f1=row["snp_f1"],
                    n_variants=row["n_variants"],
                ),
            )
            for row in rows
        ]

    def get_run(self, run_id: str) -> Run:
        for r in self.list_runs(limit=1_000_000, offset=0):
            if r.run_id == run_id:
                return r
        raise RunNotFoundError(run_id)

    def get_provenance(self, run_id: str) -> Provenance:
        query = """
            SELECT r.pipeline_version, r.git_commit, r.caller, r.started_at, r.exported_at,
                   p.truth_version, p.input_checksums
            FROM runs r
            JOIN run_provenance p ON p.run_pk = r.id
            WHERE r.run_id = %s
            ORDER BY p.recorded_at DESC LIMIT 1
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(query, [run_id])
            row = cur.fetchone()
        if row is None:
            raise RunNotFoundError(run_id)
        return Provenance(
            pipeline_version=row["pipeline_version"],
            git_commit=row["git_commit"],
            caller=row["caller"],
            started_at=row["started_at"],
            exported_at=row["exported_at"],
            truth_version=row["truth_version"],
            input_checksums=row["input_checksums"] or {},
        )

    def list_qc_warnings(self, run_id: str) -> list[QcWarning]:
        query = """
            SELECT w.sample_id, w.overall_status, w.metric_name, w.metric_value,
                   w.threshold_warn, w.threshold_fail, w.threshold_source, w.recorded_at
            FROM qc_warnings w
            JOIN runs r ON r.id = w.run_pk
            WHERE r.run_id = %s
            ORDER BY w.recorded_at DESC
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(query, [run_id])
            rows = cur.fetchall()
        return [QcWarning(run_id=run_id, **row) for row in rows]

    def create_review_decision(self, run_id: str, decision: ReviewDecisionCreate) -> ReviewDecision:
        query = """
            INSERT INTO review_decisions (run_pk, run_id, variant_key, classification, decision, reviewer, comment)
            SELECT r.id, %(run_id)s, %(variant_key)s, %(classification)s, %(decision)s, %(reviewer)s, %(comment)s
            FROM runs r WHERE r.run_id = %(run_id)s
            RETURNING id, decided_at
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(query, {"run_id": run_id, **decision.model_dump()})
            row = cur.fetchone()
            conn.commit()
        if row is None:
            raise RunNotFoundError(run_id)
        return ReviewDecision(id=row["id"], run_id=run_id, decided_at=row["decided_at"], **decision.model_dump())
