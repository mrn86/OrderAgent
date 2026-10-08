"""售后服务：经 MCP 调用 mcpserver。"""

from __future__ import annotations

from typing import Any, Optional

from app.core.agent.tools.mcp_client import call_mcp_tool


def list_after_sales(
    *,
    order_id: Optional[str] = None,
    order_no: Optional[str] = None,
    after_sale_id: Optional[str] = None,
    type_: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    del type_, status, page, page_size
    return call_mcp_tool(
        "list_after_sales",
        {
            "order_id": order_id,
            "order_no": order_no,
            "after_sale_id": after_sale_id,
        },
    )


def get_after_sale_detail(after_sale_id: str) -> dict[str, Any]:
    return call_mcp_tool("get_after_sale_detail", {"after_sale_id": after_sale_id})


def get_progress(*, order_id: Optional[str] = None, order_no: Optional[str] = None) -> dict[str, Any]:
    return call_mcp_tool(
        "get_after_sale_progress",
        {"order_id": order_id, "order_no": order_no},
    )
