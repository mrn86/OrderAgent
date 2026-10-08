"""售后工具契约。"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import Field

from schemas.common import OpenModel, StrictModel


class ListAfterSalesArgs(StrictModel):
    order_no: Optional[str] = Field(default=None, max_length=64)
    order_id: Optional[str] = Field(default=None, max_length=64)
    after_sale_id: Optional[str] = Field(default=None, max_length=64)


class ListAfterSalesResult(OpenModel):
    list: List[Any] = Field(default_factory=list)
    page: int = 1
    pageSize: int = 10
    total: int = 0
    hasMore: bool = False


class GetAfterSaleDetailArgs(StrictModel):
    after_sale_id: str = Field(..., min_length=1, max_length=64)


class AfterSaleDetailResult(OpenModel):
    afterSaleId: str
    orderId: str = ""
    orderNo: str = ""
    status: str = ""


class GetAfterSaleProgressArgs(StrictModel):
    order_no: Optional[str] = Field(default=None, max_length=64)
    order_id: Optional[str] = Field(default=None, max_length=64)


class AfterSaleProgressResult(OpenModel):
    orderId: str = ""
    orderNo: str = ""
    hasAfterSale: bool = False
    items: List[Any] = Field(default_factory=list)
