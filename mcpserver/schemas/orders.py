"""订单工具契约。"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import Field

from schemas.common import OpenModel, StrictModel


class QueryOrdersArgs(StrictModel):
    order_no: Optional[str] = Field(default=None, max_length=64)
    order_id: Optional[str] = Field(default=None, max_length=64)
    status: Optional[str] = Field(default=None, max_length=200)
    keyword: Optional[str] = Field(default=None, max_length=200)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=50)


class OrderListItem(OpenModel):
    orderId: str
    orderNo: str
    status: str
    statusText: str = ""


class QueryOrdersResult(OpenModel):
    list: List[Any] = Field(default_factory=list)
    page: int = 1
    pageSize: int = 10
    total: int = 0
    hasMore: bool = False


class GetOrderDetailArgs(StrictModel):
    order_id: str = Field(..., min_length=1, max_length=64)


class GetOrderByNoArgs(StrictModel):
    order_no: str = Field(..., min_length=1, max_length=64)


class OrderDetailResult(OpenModel):
    """订单详情：关键标识必填，其余字段随 fake/api 扩展。"""

    orderId: str
    orderNo: str
    status: str
