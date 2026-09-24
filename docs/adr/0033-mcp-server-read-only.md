# ADR-0033 — Read-only MCP server over run, QC, provenance and knowledge-base data

**Status:** Accepted · **Date:** 2026-09-24

## Context

The platform's data is reachable over REST (`api/`, [ADR-0027](0027-rest-react-frontend-for-variant-interpreter.md)),
Metabase ([ADR-0006](0006-metabase-dashboard.md)) and the Streamlit demo. None of these lets an
LLM client such as Claude Desktop or Claude Code query the data directly. The Model Context
Protocol (MCP) is the standard way to expose tools to such clients.

An MCP server gives an LLM a tool surface, and that raises two risks this platform already
guards against elsewhere:

1. **A new write path into insert-only stores.** Results and provenance are insert-only:
   Postgres `forbid_mutation()` triggers ([ADR-0005](0005-insert-only-postgres.md)) and an IAM deny
   on DynamoDB ([ADR-0012](0012-dynamodb-primary-store.md), [ADR-0031](0031-dynamodb-streams-audit-sink-accepted-limitation.md)).
   The REST API has one write, `POST /runs/{run_id}/review-decisions`, which records clinician
   sign-off ([ADR-0019](0019-reviewer-decision-log.md)). An LLM calling that on its own would fake
   the human-in-the-loop step.
2. **AI-drafted text without the guardrails.** [ADR-0008](0008-guardrails-human-in-the-loop.md)
   requires all AI output to pass `enforce_guardrails()`: the mandatory
   `AI-DRAFTED — REQUIRES CLINICIAN REVIEW` banner, a provenance line and advice-phrase scrubbing.

## Decision

Add `mcp_server/`, a **read-only** MCP server built with the official Python MCP SDK
(`FastMCP`, stdio transport). It exposes six tools: `list_runs`, `get_run_qc`,
`get_run_provenance`, `query_clinvar`, `query_gnomad` and `query_gene_info`.

- **Reuse, don't duplicate.** Run, QC and provenance data comes from `api/repository.py`. The
  server uses `FixtureRepository` by default and `PostgresRepository` when `CGP_DB_URL` is set,
  the same rule as `api/dependencies.py`. Knowledge-base lookups go through the agent's
  `ToolRegistry` (`ai-report/agent/tools.py`), and the ACMG frequency-code logic is not re-implemented.
- **Fixture-backed by default.** With no configuration the server serves `api/data/demo_runs.json`
  and the committed chr20 SQLite knowledge base. It needs no DB, AWS or network, like the API.
- **Read-only in depth, not only by omission:**
  1. A `ReadOnlyRuns` facade exposes only the repository's read methods, so
     `create_review_decision` cannot be reached.
  2. Postgres sessions are opened with `default_transaction_read_only=on`, so the database
     rejects even an INSERT, which the insert-only triggers alone would allow.
  3. The knowledge-base SQLite file is opened with `mode=ro`.
  4. Every tool carries the MCP annotations `readOnlyHint=true` and `destructiveHint=false`.
  `tests/test_mcp_server.py` asserts each of these layers, and also that no tool name suggests a
  write or report function.
- **No review-decision tool.** Sign-off stays a human action through the REST API or the web UI.
- **No report-generation or interpretation tool.** The server exposes no AI-drafted text
  (`ai-report/infer.py` reports, or `/agent/variant-review` classifications and summaries).
  Every value it returns comes from the stores or the knowledge base, so no AI-drafted text
  can reach a client without the `enforce_guardrails()` banner. The tool outputs also
  carry the "not an accredited clinical test" disclaimer and the known provenance-stamp gaps
  (docs/VALIDATION.md §6), so the provenance is not presented as complete.
- **stdio only.** It runs as a local subprocess of the client, with no network listener and no
  auth surface. An HTTP transport would need authentication and is out of scope.

## Alternatives considered

- **Wrap the REST API over HTTP from the MCP server.** Rejected: that would need a running
  uvicorn, and the write endpoint would sit one bug away. Calling the repository in-process is
  simpler, and the read-only facade removes that write path.
- **Expose the variant interpreter as a tool, with the output passed through
  `enforce_report_guardrails()`.** Deferred, not rejected. The guardrails make the text safe to
  show. But an LLM client would then pass AI-drafted classifications to another LLM, which
  weakens the human-review framing of ADR-0008 more than it helps a portfolio demo. Revisit only
  with a guardrail-asserting test that covers the MCP path.
- **Include `classify_acmg` from the agent's `ToolRegistry`.** Left out: it combines evidence
  codes into a classification, which is interpretation rather than data lookup.

## Consequences

**Good**
- Any MCP client can inspect runs, QC, validation outcomes and provenance, and query the chr20
  ClinVar/gnomAD/gene knowledge base, with no setup beyond `pip install -r mcp_server/requirements.txt`.
- The server adds no new write path into the insert-only stores, and the database enforces this
  as well as the code.

**Bad / accepted**
- `mcp` is not in `requirements-dev.txt`, so CI skips `tests/test_mcp_server.py` unless the
  SDK is installed.
- Reads under `CGP_DB_URL` use whatever role the DSN names. A dedicated `SELECT`-only Postgres
  role would be a stronger control than a read-only session default, which a client could
  override if the DSN allowed it. That role is not provisioned by `db/schema.sql`.
- The server does not read the DynamoDB primary store. It sees only the fixtures or the Postgres
  replica, like the REST API.
