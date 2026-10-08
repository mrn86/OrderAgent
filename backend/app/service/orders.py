"""订单服务：经 MCP 调用 mcpserver。"""

from __future__ import annotations

from typing import Any, Optional

from app.core.agent.tools.mcp_client import call_mcp_tool


def list_orders(
    *,
    order_no: Optional[str] = None,
    order_id: Optional[str] = None,
    status: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    del created_from, created_to  # MCP query_orders 未暴露时间过滤；REST 仍可传但忽略
    return call_mcp_tool(
        "query_orders",
        {
            "order_no": order_no,
            "order_id": order_id,
            "status": status,
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
        },
    )


def get_order_detail(
    order_id: Optional[str] = None,
    order_no: Optional[str] = None,
    *,
    include_logistics: bool = True,
    include_after_sale: bool = True,
    include_invoice: bool = True,
) -> dict[str, Any]:
    del include_logistics, include_after_sale, include_invoice
    if order_id:
        return call_mcp_tool("get_order_detail", {"order_id": order_id})
    if order_no:
        return call_mcp_tool("get_order_by_no", {"order_no": order_no})
    return {"error": {"code": 400, "message": "缺少 orderId/orderNo"}}
