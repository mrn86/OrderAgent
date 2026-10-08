"""发票服务：经 MCP 调用 mcpserver。"""

from __future__ import annotations

from typing import Any, Optional

from app.core.agent.tools.mcp_client import call_mcp_tool


def get_invoice(
    invoice_id: str,
    *,
    include_files: bool = True,
    include_progress: bool = True,
) -> dict[str, Any]:
    del include_files, include_progress
    return call_mcp_tool("get_invoice", {"invoice_id": invoice_id})


def list_by_order(
    *,
    order_id: Optional[str] = None,
    order_no: Optional[str] = None,
    status: Optional[str] = None,
    invoice_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    del status, invoice_type, page, page_size
    return call_mcp_tool(
        "list_invoices_by_order",
        {"order_id": order_id, "order_no": order_no},
    )


def create_download_urls(
    invoice_id: str,
    *,
    types: Optional[list[str]] = None,
    expire_seconds: int = 1800,
) -> dict[str, Any]:
    type_str = ",".join(str(t).strip().upper() for t in (types or ["PDF", "OFD"]) if str(t).strip())
    return call_mcp_tool(
        "create_invoice_download_urls",
        {
            "invoice_id": invoice_id,
            "types": type_str or "PDF,OFD",
            "expire_seconds": expire_seconds,
        },
    )
