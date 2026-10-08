"""按域注册 MCP 业务工具。"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from tools import after_sales, invoices, logistics, orders, refunds


def register_all(mcp: MCPServer) -> None:
    orders.register(mcp)
    after_sales.register(mcp)
    refunds.register(mcp)
    logistics.register(mcp)
    invoices.register(mcp)
