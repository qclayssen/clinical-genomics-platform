"""Read-only tool implementations for the MCP server (ADR-0033).

These are plain functions with no dependency on the `mcp` package, so they can
be unit-tested directly (tests/test_mcp_server.py) and are registered with
FastMCP in `mcp_server/server.py`.

No logic is duplicated here:

- Run / QC / provenance data comes from the REST API's repository layer
  (`api/repository.py`): `FixtureRepository` by default, `PostgresRepository`
  when `CGP_DB_URL` is set — the same selection rule as `api/dependencies.py`.
- ClinVar / gnomAD / gene-info lookups go through the agent's existing
  `ToolRegistry` (`ai-report/agent/tools.py`) over the committed chr20 SQLite
  knowledge base.

Read-only is enforced in three layers, not just by omission:

1. Only read methods are reachable: `ReadOnlyRuns` wraps the repository and
   exposes list/get calls only — `create_review_decision` is never exposed.
2. Postgres sessions are opened with `default_transaction_read_only=on`, so
   even a coding mistake here cannot INSERT into the insert-only stores
   (whose `forbid_mutation()` triggers already reject UPDATE/DELETE).
3. The knowledge-base SQLite file is opened with `mode=ro`.

No report-generation / AI-drafted text is exposed at all — see ADR-0033.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_AI_REPORT_DIR = _REPO_ROOT / "ai-report"
# Same bootstrapping as api/routers/agent.py: ai-report/ is not a package
# root, so `agent` is imported as a bare top-level module.
for _p in (_REPO_ROOT, _AI_REPORT_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from agent.data.knowledge_base import KnowledgeBase  # noqa: E402
from agent.tools import ToolRegistry  # noqa: E402

from api.repository import FixtureRepository, PostgresRepository, Repository  # noqa: E402

#: Acceptance criterion from docs/VALIDATION.md / ADR-0003, surfaced alongside QC.
SNV_F1_ACCEPTANCE = 0.99

MAX_LIMIT = 500

DISCLAIMER = (
    "Portfolio project, not an accredited clinical test. Data served here must not be "
    "used for clinical decision-making."
)

PROVENANCE_SCOPE_NOTE = (
    "Known gaps (docs/VALIDATION.md §6): input_checksums cover only the derived "
    "MarkDuplicates/hap.py artifacts, not the reads, reference or truth set; no container "
    "digest or tool version is recorded in the stamp."
)


# ─── Read-only backends ───────────────────────────────────────────────────────


class ReadOnlyPostgresRepository(PostgresRepository):
    """PostgresRepository whose every session is a read-only transaction."""

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(
            self._dsn, row_factory=dict_row, options="-c default_transaction_read_only=on"
        )


class ReadOnlyKnowledgeBase(KnowledgeBase):
    """KnowledgeBase that opens the SQLite file with `mode=ro`."""

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            self._conn.row_factory = sqlite3.Row
        return self._conn


class ReadOnlyRuns:
    """Facade over a Repository exposing only its read methods."""

    def __init__(self, repository: Repository):
        self._repo = repository

    def list_runs(self, sample_id, caller, validation_pass, limit, offset):
        return self._repo.list_runs(sample_id, caller, validation_pass, limit, offset)

    def get_run(self, run_id: str):
        return self._repo.get_run(run_id)

    def get_provenance(self, run_id: str):
        return self._repo.get_provenance(run_id)

    def list_qc_warnings(self, run_id: str):
        return self._repo.list_qc_warnings(run_id)


_runs: ReadOnlyRuns | None = None


def get_runs() -> ReadOnlyRuns:
    """Backend selection mirrors api/dependencies.py: fixtures unless CGP_DB_URL is set."""
    global _runs
    if _runs is None:
        dsn = os.environ.get("CGP_DB_URL")
        repo: Repository = ReadOnlyPostgresRepository(dsn) if dsn else FixtureRepository()
        _runs = ReadOnlyRuns(repo)
    return _runs


def set_runs_backend(repository: Repository | None) -> None:
    """Override (or reset, with None) the run backend — used by tests."""
    global _runs
    _runs = ReadOnlyRuns(repository) if repository is not None else None


# ─── Run / QC / provenance tools ──────────────────────────────────────────────


def list_runs(
    sample_id: str | None = None,
    caller: str | None = None,
    validation_pass: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List pipeline runs with their headline QC metrics, optionally filtered."""
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))
    runs = get_runs().list_runs(sample_id, caller, validation_pass, limit, offset)
    return [r.model_dump(mode="json") for r in runs]


def get_run_qc(run_id: str) -> dict[str, Any]:
    """Return a run's latest QC metrics, hap.py validation outcome and QC warnings."""
    backend = get_runs()
    run = backend.get_run(run_id)
    warnings = backend.list_qc_warnings(run_id)
    return {
        "run_id": run.run_id,
        "sample_id": run.sample_id,
        "caller": run.caller,
        "pipeline_version": run.pipeline_version,
        "validation_pass": run.validation_pass,
        "snv_f1_acceptance_threshold": SNV_F1_ACCEPTANCE,
        "qc": run.qc.model_dump(mode="json"),
        "qc_warnings": [w.model_dump(mode="json") for w in warnings],
        "disclaimer": DISCLAIMER,
    }


def get_run_provenance(run_id: str) -> dict[str, Any]:
    """Return a run's full provenance stamp, plus a note on its known gaps."""
    prov = get_runs().get_provenance(run_id)
    return {
        "run_id": run_id,
        "provenance": prov.model_dump(mode="json"),
        "scope_note": PROVENANCE_SCOPE_NOTE,
    }


# ─── Knowledge-base tools (reuse ai-report/agent/tools.py) ────────────────────


def _invoke_kb_tool(name: str, **kwargs: Any) -> dict[str, Any]:
    # A fresh read-only KB per call: cheap (local SQLite) and avoids sharing a
    # sqlite3 connection across the server's worker threads.
    registry = ToolRegistry(kb=ReadOnlyKnowledgeBase())
    try:
        result = registry.invoke(name, kwargs)
    finally:
        registry.close()
    if not result.success:
        raise ValueError(result.error or f"{name} failed")
    return result.output


def query_clinvar(chrom: str, pos: int, ref: str, alt: str) -> dict[str, Any]:
    """Look up ClinVar clinical significance for a chr20 variant (local knowledge base)."""
    return _invoke_kb_tool("query_clinvar", chrom=chrom, pos=int(pos), ref=ref, alt=alt)


def query_gnomad(chrom: str, pos: int, ref: str, alt: str) -> dict[str, Any]:
    """Look up gnomAD allele frequency and ACMG frequency evidence for a chr20 variant."""
    return _invoke_kb_tool("query_gnomad", chrom=chrom, pos=int(pos), ref=ref, alt=alt)


def query_gene_info(gene_symbol: str) -> dict[str, Any]:
    """Return gene coordinates, description and ClinVar landscape for a chr20 gene."""
    return _invoke_kb_tool("query_gene_info", gene_symbol=gene_symbol)


#: Every tool the server exposes. All are read-only; nothing here writes.
TOOLS = (list_runs, get_run_qc, get_run_provenance, query_clinvar, query_gnomad, query_gene_info)
