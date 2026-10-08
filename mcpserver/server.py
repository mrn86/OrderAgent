"""Order Agent 业务 MCP Server（Streamable HTTP）。"""

from __future__ import annotations

import path_setup  # noqa: F401

from mcp.server.mcpserver import MCPServer

from tools import register_all

mcp = MCPServer(
    name="order-agent-mcp",
    version="1.5.0",
    instructions=(
        "E-commerce business tools: orders, after-sales, refunds, logistics, invoices. "
        "Input/output are Pydantic-validated; errors use {error: {code, message}}."
    ),
)

register_all(mcp)
