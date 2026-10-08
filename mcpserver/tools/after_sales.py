"""售后 MCP tools。"""

from __future__ import annotations

from typing import Annotated, Optional

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from schemas.after_sales import (
    AfterSaleDetailResult,
    AfterSaleProgressResult,
    GetAfterSaleDetailArgs,
    GetAfterSaleProgressArgs,
    ListAfterSalesArgs,
    ListAfterSalesResult,
)
from schemas.common import ToolErrorResult, as_tool_result
from service import after_sales as after_sale_service


def register(mcp: MCPServer) -> None:
    @mcp.tool(name="list_after_sales", description="查询售后单列表。")
    def list_after_sales(
        order_no: Annotated[Optional[str], Field(default=None, max_length=64)] = None,
        order_id: Annotated[Optional[str], Field(default=None, max_length=64)] = None,
        after_sale_id: Annotated[Optional[str], Field(default=None, max_length=64)] = None,
    ) -> ListAfterSalesResult | ToolErrorResult:
        args = ListAfterSalesArgs(
            order_no=order_no,
            order_id=order_id,
            after_sale_id=after_sale_id,
        )
        data = after_sale_service.list_after_sales(
            order_id=args.order_id,
            order_no=args.order_no,
            after_sale_id=args.after_sale_id,
        )
        return as_tool_result(ListAfterSalesResult, data)

    @mcp.tool(name="get_after_sale_detail", description="查询售后详情与完整进度。")
    def get_after_sale_detail(
        after_sale_id: Annotated[str, Field(min_length=1, max_length=64)],
    ) -> AfterSaleDetailResult | ToolErrorResult:
        args = GetAfterSaleDetailArgs(after_sale_id=after_sale_id)
        data = after_sale_service.get_after_sale_detail(args.after_sale_id)
        return as_tool_result(AfterSaleDetailResult, data)

    @mcp.tool(name="get_after_sale_progress", description="按订单查询退货退款进度摘要。")
    def get_after_sale_progress(
        order_no: Annotated[Optional[str], Field(default=None, max_length=64)] = None,
        order_id: Annotated[Optional[str], Field(default=None, max_length=64)] = None,
    ) -> AfterSaleProgressResult | ToolErrorResult:
        args = GetAfterSaleProgressArgs(order_no=order_no, order_id=order_id)
        data = after_sale_service.get_progress(
            order_id=args.order_id,
            order_no=args.order_no,
        )
        return as_tool_result(AfterSaleProgressResult, data)
