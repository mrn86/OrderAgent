"""退款工具契约。"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import Field

from schemas.common import OpenModel, StrictModel


class ListRefundsArgs(StrictModel):
    order_no: Optional[str] = Field(default=None, max_length=64)
    order_id: Optional[str] = Field(default=None, max_length=64)


class ListRefundsResult(OpenModel):
    list: List[Any] = Field(default_factory=list)
    page: int = 1
    pageSize: int = 10
    total: int = 0
    hasMore: bool = False


class GetRefundDetailArgs(StrictModel):
    refund_id: str = Field(..., min_length=1, max_length=64)


class RefundDetailResult(OpenModel):
    refundId: str
    orderId: str = ""
    orderNo: str = ""
    status: str = ""


class GetRefundProgressArgs(StrictModel):
    order_no: Optional[str] = Field(default=None, max_length=64)
    order_id: Optional[str] = Field(default=None, max_length=64)


class RefundProgressResult(OpenModel):
    orderId: str = ""
    orderNo: str = ""
    hasRefund: bool = False
    totalRefundAmount: int = 0
    currency: str = "CNY"
    items: List[Any] = Field(default_factory=list)


class CreateRefundArgs(StrictModel):
    amount: int = Field(..., ge=1, description="退款金额，单位分")
    reason: str = Field(..., min_length=4, max_length=200)
    order_no: Optional[str] = Field(default=None, max_length=64)
    order_id: Optional[str] = Field(default=None, max_length=64)
    after_sale_id: Optional[str] = Field(default=None, max_length=64)


class CreateRefundResult(OpenModel):
    refundId: str = ""
    orderId: str = ""
    orderNo: str = ""
    status: str = ""
    refundAmount: int = 0
