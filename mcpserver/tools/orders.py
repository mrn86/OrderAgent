"""订单查询 MCP tools。"""

from __future__ import annotations

from typing import Annotated, Optional

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from schemas.common import ToolErrorResult, as_tool_result
from schemas.orders import (
    GetOrderByNoArgs,
    GetOrderDetailArgs,
    OrderDetailResult,
    QueryOrdersArgs,
    QueryOrdersResult,
)
from service import orders as order_service

QUERY_ORDERS_DESC = (
    "查询订单列表；过滤条件均可选，无订单号也可直接调用拉取当前用户订单。"
    "用户说「查看全部订单/我的订单/订单列表」时调用一次即可，用返回的 list 直接作答，"
    "禁止再对每一笔调用详情/物流工具，除非用户明确要某一笔的明细。"
    "同一查询条件成功返回后不要重复调用。"
    "用户说「给我退款/我的订单退款/帮我退款」等且未给订单号时，必须先调用本工具定位订单，"
    "禁止一上来只追问订单号。"
    "仅 1 笔：用其 order_no/order_id 继续后续操作；多笔：列出摘要请用户选择。"
    "用户说「第N笔/第二笔/上一笔/那笔订单」时，同样先取列表再按序号定位，不要因缺订单号就转人工。"
)


def register(mcp: MCPServer) -> None:
    @mcp.tool(name="query_orders", description=QUERY_ORDERS_DESC)
    def query_orders(
        order_no: Annotated[Optional[str], Field(default=None, max_length=64)] = None,
        order_id: Annotated[Optional[str], Field(default=None, max_length=64)] = None,
        status: Annotated[Optional[str], Field(default=None, max_length=200)] = None,
        keyword: Annotated[Optional[str], Field(default=None, max_length=200)] = None,
        page: Annotated[int, Field(default=1, ge=1)] = 1,
        page_size: Annotated[int, Field(default=10, ge=1, le=50)] = 10,
    ) -> QueryOrdersResult | ToolErrorResult:
        args = QueryOrdersArgs(
            order_no=order_no,
            order_id=order_id,
            status=status,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )
        data = order_service.list_orders(**args.model_dump())
        return as_tool_result(QueryOrdersResult, data)

    @mcp.tool(name="get_order_detail", description="按内部订单ID查询订单详情。")
    def get_order_detail(
        order_id: Annotated[str, Field(min_length=1, max_length=64)],
    ) -> OrderDetailResult | ToolErrorResult:
        args = GetOrderDetailArgs(order_id=order_id)
        data = order_service.get_order_detail(order_id=args.order_id)
        return as_tool_result(OrderDetailResult, data)

    @mcp.tool(name="get_order_by_no", description="按对外订单号查询订单详情。")
    def get_order_by_no(
        order_no: Annotated[str, Field(min_length=1, max_length=64)],
    ) -> OrderDetailResult | ToolErrorResult:
        args = GetOrderByNoArgs(order_no=order_no)
        data = order_service.get_order_detail(order_no=args.order_no)
        return as_tool_result(OrderDetailResult, data)
