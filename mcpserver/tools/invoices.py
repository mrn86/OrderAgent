"""发票 MCP tools。"""

from __future__ import annotations

from typing import Annotated, Optional

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from schemas.common import ToolErrorResult, as_tool_result
from schemas.invoices import (
    CreateInvoiceDownloadUrlsArgs,
    GetInvoiceArgs,
    InvoiceDetailResult,
    InvoiceDownloadUrlsResult,
    ListInvoicesByOrderArgs,
    ListInvoicesByOrderResult,
)
from service import invoices as invoice_service

GET_INVOICE_DESC = (
    "按发票 ID 查看发票详情。用户已给出 INV 开头的发票 ID 时必须用本工具，"
    "不要用 list_invoices_by_order，也不要把发票 ID 当成订单号。"
    "返回不含发信动作；禁止编造「已发送邮箱/短信」等未实现能力。"
)
LIST_INVOICES_DESC = (
    "仅在用户给的是订单号/订单 ID、还没有发票 ID 时，按订单查发票列表。"
    "参数只能是 order_no 或 order_id；禁止传入发票 ID（INV…）。"
)
DOWNLOAD_URLS_DESC = (
    "按发票 ID 生成下载链接（仅生成链接，不发送邮件）。"
    "已有 INV 开头的发票 ID 时直接调用，不必先列表。"
    "types 为 PDF/OFD/XML，逗号分隔，大小写均可；未指定用 PDF,OFD。"
    "一次成功后立即把链接交给用户，禁止重复调用本工具；禁止声称已发送邮箱。"
)


def register(mcp: MCPServer) -> None:
    @mcp.tool(name="get_invoice", description=GET_INVOICE_DESC)
    def get_invoice(
        invoice_id: Annotated[str, Field(min_length=1, max_length=64)],
    ) -> InvoiceDetailResult | ToolErrorResult:
        args = GetInvoiceArgs(invoice_id=invoice_id)
        data = invoice_service.get_invoice(args.invoice_id)
        return as_tool_result(InvoiceDetailResult, data)

    @mcp.tool(name="list_invoices_by_order", description=LIST_INVOICES_DESC)
    def list_invoices_by_order(
        order_no: Annotated[Optional[str], Field(default=None, max_length=64)] = None,
        order_id: Annotated[Optional[str], Field(default=None, max_length=64)] = None,
    ) -> ListInvoicesByOrderResult | ToolErrorResult:
        args = ListInvoicesByOrderArgs(order_no=order_no, order_id=order_id)
        data = invoice_service.list_by_order(
            order_id=args.order_id,
            order_no=args.order_no,
        )
        return as_tool_result(ListInvoicesByOrderResult, data)

    @mcp.tool(name="create_invoice_download_urls", description=DOWNLOAD_URLS_DESC)
    def create_invoice_download_urls(
        invoice_id: Annotated[str, Field(min_length=1, max_length=64)],
        types: Annotated[str, Field(default="PDF,OFD", max_length=64)] = "PDF,OFD",
        expire_seconds: Annotated[int, Field(default=1800, ge=900, le=3600)] = 1800,
    ) -> InvoiceDownloadUrlsResult | ToolErrorResult:
        args = CreateInvoiceDownloadUrlsArgs(
            invoice_id=invoice_id,
            types=types,
            expire_seconds=expire_seconds,
        )
        type_list = [t.strip().upper() for t in (args.types or "PDF").split(",") if t.strip()]
        data = invoice_service.create_download_urls(
            args.invoice_id,
            types=type_list or ["PDF"],
            expire_seconds=args.expire_seconds,
        )
        return as_tool_result(InvoiceDownloadUrlsResult, data)
