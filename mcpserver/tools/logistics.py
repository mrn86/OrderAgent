"""物流 MCP tools。"""

from __future__ import annotations

from typing import Annotated, Optional

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from schemas.common import ToolErrorResult, as_tool_result
from schemas.logistics import (
    GetLogisticsByOrderNoArgs,
    GetLogisticsTrackingArgs,
    LogisticsByOrderResult,
    LogisticsTrackingResult,
)
from service import logistics as logistics_service


def register(mcp: MCPServer) -> None:
    @mcp.tool(name="get_logistics_by_order_no", description="按订单号查询物流轨迹与时效预测。")
    def get_logistics_by_order_no(
        order_no: Annotated[str, Field(min_length=1, max_length=64)],
        include_eta: bool = True,
    ) -> LogisticsByOrderResult | ToolErrorResult:
        args = GetLogisticsByOrderNoArgs(order_no=order_no, include_eta=include_eta)
        data = logistics_service.get_by_order_no(
            args.order_no,
            include_eta=args.include_eta,
        )
        return as_tool_result(LogisticsByOrderResult, data)

    @mcp.tool(name="get_logistics_tracking", description="按运单号查询物流轨迹。")
    def get_logistics_tracking(
        tracking_no: Annotated[str, Field(min_length=1, max_length=64)],
        express_company_code: Annotated[
            Optional[str], Field(default=None, max_length=32)
        ] = None,
        include_eta: bool = True,
    ) -> LogisticsTrackingResult | ToolErrorResult:
        args = GetLogisticsTrackingArgs(
            tracking_no=tracking_no,
            express_company_code=express_company_code,
            include_eta=include_eta,
        )
        data = logistics_service.get_by_tracking(
            args.tracking_no,
            express_company_code=args.express_company_code,
            include_eta=args.include_eta,
        )
        return as_tool_result(LogisticsTrackingResult, data)
