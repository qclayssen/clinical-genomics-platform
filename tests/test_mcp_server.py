"""Tests for the read-only MCP server (mcp_server/, ADR-0033).

Tool functions are called directly against the fixture backend and the
committed chr20 knowledge base — no DB, AWS or network needed. The whole
module skips cleanly if the `mcp` SDK isn't installed.
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

pytest.importorskip("mcp")

from api.repository import RunNotFoundError  # noqa: E402
from mcp_server import tools  # noqa: E402
from mcp_server.server import build_server  # noqa: E402

EXPECTED_TOOLS = {
    "list_runs",
    "get_run_qc",
    "get_run_provenance",
    "query_clinvar",
    "query_gnomad",
    "query_gene_info",
}


@pytest.fixture(autouse=True)
def _fixture_backend(monkeypatch):
    monkeypatch.delenv("CGP_DB_URL", raising=False)
    tools.set_runs_backend(None)
    yield
    tools.set_runs_backend(None)


# ─── Runs / QC / provenance ───────────────────────────────────────────────────


def test_list_runs_returns_fixture_runs():
    runs = tools.list_runs()
    assert {r["run_id"] for r in runs} == {"run_2026_0301_a", "run_2026_0308_b", "run_2026_0315_c"}


def test_list_runs_filters_and_clamps_limit():
    assert [r["run_id"] for r in tools.list_runs(caller="deepvariant")] == ["run_2026_0315_c"]
    assert [r["run_id"] for r in tools.list_runs(validation_pass=False)] == ["run_2026_0315_c"]
    assert len(tools.list_runs(limit=0)) == 1  # clamped to >= 1
    assert len(tools.list_runs(limit=10_000)) == 3  # clamped to MAX_LIMIT, not an error


def test_get_run_qc_includes_warnings_and_threshold():
    qc = tools.get_run_qc("run_2026_0308_b")
    assert qc["qc"]["snp_f1"] == pytest.approx(0.9857)
    assert qc["snv_f1_acceptance_threshold"] == 0.99
    assert [w["metric_name"] for w in qc["qc_warnings"]] == ["percent_duplication"]
    assert "not an accredited clinical test" in qc["disclaimer"]


def test_get_run_provenance_has_stamp_and_known_gaps():
    out = tools.get_run_provenance("run_2026_0301_a")
    prov = out["provenance"]
    for field in ("pipeline_version", "git_commit", "reference_build", "truth_version", "input_checksums"):
        assert prov[field]
    assert "not the reads, reference or truth set" in out["scope_note"]


@pytest.mark.parametrize("fn", [tools.get_run_qc, tools.get_run_provenance])
def test_unknown_run_raises(fn):
    with pytest.raises(RunNotFoundError):
        fn("no_such_run")


# ─── Knowledge-base tools ─────────────────────────────────────────────────────


def test_query_clinvar_known_variant():
    out = tools.query_clinvar("chr20", 4699605, "G", "A")
    assert out["found"] is True
    assert out["records"][0]["clinical_significance"] == "Pathogenic"


def test_query_clinvar_unknown_variant():
    assert tools.query_clinvar("chr20", 1, "A", "C")["found"] is False


def test_query_gnomad_known_variant():
    out = tools.query_gnomad("chr20", 4699605, "G", "A")
    assert out["found"] is True
    assert "PM2" in out["acmg_frequency_codes"]


def test_query_gene_info():
    assert tools.query_gene_info("PRNP")["gene_symbol"] == "PRNP"
    assert tools.query_gene_info("NOT_A_GENE")["found"] is False


# ─── Read-only guarantees ─────────────────────────────────────────────────────


def test_readonly_facade_has_no_write_path():
    runs = tools.get_runs()
    assert not hasattr(runs, "create_review_decision")
    public = {n for n in dir(runs) if not n.startswith("_")}
    assert public == {"list_runs", "get_run", "get_provenance", "list_qc_warnings"}


def test_knowledge_base_connection_is_read_only():
    kb = tools.ReadOnlyKnowledgeBase()
    try:
        conn = kb._get_conn()
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE should_fail (x INTEGER)")
    finally:
        kb.close()


def test_postgres_backend_forces_read_only_sessions(monkeypatch):
    captured = {}

    class _FakePsycopg:
        @staticmethod
        def connect(dsn, **kwargs):
            captured.update(dsn=dsn, **kwargs)
            return object()

    import sys
    import types

    rows = types.ModuleType("psycopg.rows")
    rows.dict_row = object()
    fake = types.ModuleType("psycopg")
    fake.connect = _FakePsycopg.connect
    fake.rows = rows
    monkeypatch.setitem(sys.modules, "psycopg", fake)
    monkeypatch.setitem(sys.modules, "psycopg.rows", rows)

    tools.ReadOnlyPostgresRepository("postgresql://example/db")._connect()
    assert "default_transaction_read_only=on" in captured["options"]


def test_cgp_db_url_selects_read_only_postgres(monkeypatch):
    monkeypatch.setenv("CGP_DB_URL", "postgresql://example/db")
    tools.set_runs_backend(None)
    assert isinstance(tools.get_runs()._repo, tools.ReadOnlyPostgresRepository)


# ─── Server registration ──────────────────────────────────────────────────────


def test_server_registers_exactly_the_read_only_tools():
    listed = asyncio.run(build_server().list_tools())
    assert {t.name for t in listed} == EXPECTED_TOOLS
    for t in listed:
        assert t.annotations.readOnlyHint is True
        assert t.annotations.destructiveHint is False


def test_no_report_or_write_tools_exposed():
    names = {t.name for t in asyncio.run(build_server().list_tools())}
    forbidden = ("report", "review", "decision", "create", "insert", "update", "delete", "write")
    assert not any(word in name for name in names for word in forbidden)
