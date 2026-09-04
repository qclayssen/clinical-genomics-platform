"""Unit tests for PostgresRepository's SQL-to-model mapping.

No real Postgres needed: _connect() is monkeypatched with a fake
connection/cursor that returns canned rows, so these exercise the exact
mapping/query-construction bugs a live DB would otherwise hide until
integration time.
"""

from __future__ import annotations

from datetime import datetime, timezone

from api.repository import PostgresRepository, RunNotFoundError


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.last_query = None
        self.last_params = None

    def execute(self, query, params=None):
        self.last_query = query
        self.last_params = params

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def make_repo(rows) -> tuple[PostgresRepository, FakeCursor]:
    repo = PostgresRepository(dsn="postgresql://unused")
    cursor = FakeCursor(rows)
    repo._connect = lambda: FakeConnection(cursor)  # type: ignore[method-assign]
    return repo, cursor


RUN_ROW_NO_QC = {
    "run_id": "run_new",
    "sample_id": "HG002_chr20",
    "pipeline_version": "0.3.0",
    "caller": "gatk",
    "validation_pass": False,
    "started_at": datetime.now(timezone.utc),
    "exported_at": None,
    "percent_duplication": None,
    "snp_precision": None,
    "snp_recall": None,
    "snp_f1": None,
    "n_variants": None,
}


def test_row_with_no_qc_metrics_does_not_crash():
    """A run inserted before its qc_metrics row exists must not 500."""
    repo, _ = make_repo([RUN_ROW_NO_QC])
    run = repo.get_run("run_new")
    assert run.run_id == "run_new"
    assert run.qc.snp_f1 is None


def test_list_runs_maps_rows():
    repo, _ = make_repo([RUN_ROW_NO_QC])
    runs = repo.list_runs()
    assert len(runs) == 1
    assert runs[0].sample_id == "HG002_chr20"


def test_get_run_filters_by_run_id_in_sql():
    repo, cursor = make_repo([RUN_ROW_NO_QC])
    repo.get_run("run_new")
    assert "r.run_id = %s" in cursor.last_query
    assert cursor.last_params == ["run_new", 1, 0]


def test_get_run_not_found_when_no_rows():
    repo, _ = make_repo([])
    try:
        repo.get_run("missing")
        assert False, "expected RunNotFoundError"
    except RunNotFoundError:
        pass
