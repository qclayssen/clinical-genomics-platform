# Read-only MCP server

A [Model Context Protocol](https://modelcontextprotocol.io) server that lets any MCP client
(Claude Desktop, Claude Code, …) **read** the platform's run, QC, provenance and chr20
knowledge-base data. Built on the official Python MCP SDK (`FastMCP`, stdio transport).
Design rationale: [ADR-0033](../docs/adr/0033-mcp-server-read-only.md).

> Portfolio project, not an accredited clinical test. Nothing served here is for clinical
> decision-making.

## Tools

All tools are annotated `readOnlyHint=true`, `destructiveHint=false`. There are **no write
tools and no report-generation tools**.

| Tool | Arguments | Backed by |
|---|---|---|
| `list_runs` | `sample_id?`, `caller?`, `validation_pass?`, `limit` (1–500), `offset` | `api/repository.py` |
| `get_run_qc` | `run_id` | `api/repository.py` (run QC + QC warnings, SNV F1 ≥ 0.99 threshold) |
| `get_run_provenance` | `run_id` | `api/repository.py` (provenance stamp + note on its known gaps) |
| `query_clinvar` | `chrom`, `pos`, `ref`, `alt` | `ai-report/agent/tools.py` → local chr20 SQLite KB |
| `query_gnomad` | `chrom`, `pos`, `ref`, `alt` | `ai-report/agent/tools.py` → local chr20 SQLite KB |
| `query_gene_info` | `gene_symbol` | `ai-report/agent/tools.py` → local chr20 SQLite KB |

An unknown `run_id` comes back as an MCP tool error (`isError: true`).

## Run

```bash
pip install -r mcp_server/requirements.txt
python -m mcp_server              # from the repo root; speaks MCP over stdio
```

By default it serves the committed fixtures (`api/data/demo_runs.json`), so it needs no
database, AWS, or network. Set `CGP_DB_URL` to read a live Postgres built from
`db/schema.sql` instead. Every session is then opened with
`default_transaction_read_only=on`.

Try it interactively with the MCP Inspector: `npx @modelcontextprotocol/inspector python -m mcp_server`.

## Client configuration

**Claude Code** (from the repo root):

```bash
claude mcp add cgp-readonly -- python /absolute/path/to/clinical-genomics-platform/mcp_server/server.py
# optionally against Postgres:
claude mcp add cgp-readonly -e CGP_DB_URL=postgresql://reader@localhost/cgp -- \
  python /absolute/path/to/clinical-genomics-platform/mcp_server/server.py
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "cgp-readonly": {
      "command": "/absolute/path/to/python",
      "args": ["/absolute/path/to/clinical-genomics-platform/mcp_server/server.py"]
    }
  }
}
```

Use the Python interpreter that has `mcp_server/requirements.txt` installed. Launching
`server.py` by path works from any working directory, because it puts the repo root on
`sys.path` itself.

## Tests

```bash
pytest tests/test_mcp_server.py   # skips cleanly if `mcp` is not installed
```
