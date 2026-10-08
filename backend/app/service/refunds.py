"""退款服务：经 MCP 调用 mcpserver。"""

from __future__ import annotations

from typing import Any, Optional

from app.core.agent.tools.mcp_client import call_mcp_tool


def list_refunds(
    *,
    order_id: Optional[str] = None,
    order_no: Optional[str] = None,
    refund_id: Optional[str] = None,
    after_sale_id: Optional[str] = None,
    status: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    del refund_id, after_sale_id, status, created_from, created_to, page, page_size
    return call_mcp_tool(
        "list_refunds",
        {"order_id": order_id, "order_no": order_no},
    )


def get_refund_detail(refund_id: str) -> dict[str, Any]:
    return call_mcp_tool("get_refund_detail", {"refund_id": refund_id})


def get_progress(*, order_id: Optional[str] = None, order_no: Optional[str] = None) -> dict[str, Any]:
    return call_mcp_tool(
        "get_refund_progress",
        {"order_id": order_id, "order_no": order_no},
    )


def create_refund(
    *,
    order_id: Optional[str] = None,
    order_no: Optional[str] = None,
    amount: int,
    reason: str,
    after_sale_id: Optional[str] = None,
) -> dict[str, Any]:
    return call_mcp_tool(
        "create_refund",
        {
            "order_id": order_id,
            "order_no": order_no,
            "amount": amount,
            "reason": reason,
            "after_sale_id": after_sale_id,
        },
    )
