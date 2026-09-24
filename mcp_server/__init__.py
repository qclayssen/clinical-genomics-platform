"""Read-only MCP server for the Clinical Genomics Insight Platform (ADR-0033).

`mcp_server.tools` holds the plain tool functions (no `mcp` dependency, so they
are unit-testable anywhere); `mcp_server.server` registers them with the
official Python MCP SDK's FastMCP over stdio.
"""
