"""退款 MCP tools。"""

from __future__ import annotations

from typing import Annotated, Optional

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from schemas.common import ToolErrorResult, as_tool_result
from schemas.refunds import (
    CreateRefundArgs,
    CreateRefundResult,
    GetRefundDetailArgs,
    GetRefundProgressArgs,
    ListRefundsArgs,
    ListRefundsResult,
    RefundDetailResult,
    RefundProgressResult,
)
from service import refunds as refund_service

CREATE_REFUND_DESC = (
    "为指定订单发起仅退款申请。"
    "调用前须已定位订单（order_no 或 order_id 二选一）；"
    "用户要退款但未提供订单号时，不要直接追问订单号，先调用查询订单列表工具定位后再回来调用本工具。"
    "amount 为整数、单位分（如 29900=299.00 元）；不明时用订单实付 payAmount（分）。"
    "reason 不少于 4 字，须为用户明确提供的退款原因；未说明原因时不要调用，先向用户确认。"
    "禁止空原因、占位原因或编造原因。"
)


def register(mcp: MCPServer) -> None:
    @mcp.tool(name="list_refunds", description="查询退款列表。")
    def list_refunds(
        order_no: Annotated[Optional[str], Field(default=None, max_length=64)] = None,
        order_id: Annotated[Optional[str], Field(default=None, max_length=64)] = None,
    ) -> ListRefundsResult | ToolErrorResult:
        args = ListRefundsArgs(order_no=order_no, order_id=order_id)
        data = refund_service.list_refunds(
            order_id=args.order_id,
            order_no=args.order_no,
        )
        return as_tool_result(ListRefundsResult, data)

    @mcp.tool(name="get_refund_detail", description="查询退款详情与进度。")
    def get_refund_detail(
        refund_id: Annotated[str, Field(min_length=1, max_length=64)],
    ) -> RefundDetailResult | ToolErrorResult:
        args = GetRefundDetailArgs(refund_id=refund_id)
        data = refund_service.get_refund_detail(args.refund_id)
        return as_tool_result(RefundDetailResult, data)

    @mcp.tool(name="get_refund_progress", description="按订单查询退款进度。")
    def get_refund_progress(
        order_no: Annotated[Optional[str], Field(default=None, max_length=64)] = None,
        order_id: Annotated[Optional[str], Field(default=None, max_length=64)] = None,
    ) -> RefundProgressResult | ToolErrorResult:
        args = GetRefundProgressArgs(order_no=order_no, order_id=order_id)
        data = refund_service.get_progress(
            order_id=args.order_id,
            order_no=args.order_no,
        )
        return as_tool_result(RefundProgressResult, data)

    @mcp.tool(name="create_refund", description=CREATE_REFUND_DESC)
    def create_refund(
        amount: Annotated[int, Field(ge=1, description="退款金额，单位分")],
        reason: Annotated[str, Field(min_length=4, max_length=200)],
        order_no: Annotated[Optional[str], Field(default=None, max_length=64)] = None,
        order_id: Annotated[Optional[str], Field(default=None, max_length=64)] = None,
        after_sale_id: Annotated[Optional[str], Field(default=None, max_length=64)] = None,
    ) -> CreateRefundResult | ToolErrorResult:
        args = CreateRefundArgs(
            amount=amount,
            reason=reason,
            order_no=order_no,
            order_id=order_id,
            after_sale_id=after_sale_id,
        )
        data = refund_service.create_refund(
            order_id=args.order_id,
            order_no=args.order_no,
            amount=args.amount,
            reason=args.reason,
            after_sale_id=args.after_sale_id,
        )
        return as_tool_result(CreateRefundResult, data)
