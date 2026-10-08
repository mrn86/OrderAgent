"""物流服务：经 MCP 调用 mcpserver。"""

from __future__ import annotations

from typing import Any, Optional

from app.core.agent.tools.mcp_client import call_mcp_tool


def get_by_order_no(order_no: str, *, include_eta: bool = True) -> dict[str, Any]:
    return call_mcp_tool(
        "get_logistics_by_order_no",
        {"order_no": order_no, "include_eta": include_eta},
    )


def get_by_tracking(
    tracking_no: str,
    *,
    express_company_code: Optional[str] = None,
    include_eta: bool = True,
) -> dict[str, Any]:
    return call_mcp_tool(
        "get_logistics_tracking",
        {
            "tracking_no": tracking_no,
            "express_company_code": express_company_code,
            "include_eta": include_eta,
        },
    )
