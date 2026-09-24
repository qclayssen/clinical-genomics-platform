"""Read-only MCP server (stdio) for the Clinical Genomics Insight Platform.

Run from the repo root:

    pip install -r mcp_server/requirements.txt
    python -m mcp_server            # or: python mcp_server/server.py

Fixture-backed by default; set CGP_DB_URL to read a live Postgres instead
(sessions are forced read-only). See mcp_server/README.md and ADR-0033.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    # Launched as a script (e.g. from a Claude Desktop config): put the repo
    # root on sys.path so `mcp_server`, `api` and `agent` resolve.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from mcp_server import tools  # noqa: E402

INSTRUCTIONS = (
    "Read-only access to the Clinical Genomics Insight Platform (germline SNV, GIAB HG002, "
    "GRCh38 chr20): pipeline runs, QC metrics, hap.py validation outcomes, provenance stamps, "
    "and a local chr20 ClinVar/gnomAD/gene knowledge base. There are no write tools and no "
    "report-generation tools. " + tools.DISCLAIMER
)

READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)


def build_server() -> FastMCP:
    server = FastMCP("clinical-genomics-platform", instructions=INSTRUCTIONS)
    for fn in tools.TOOLS:
        server.tool(annotations=READ_ONLY)(fn)
    return server


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
