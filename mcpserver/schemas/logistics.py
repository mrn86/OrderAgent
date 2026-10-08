"""物流工具契约。"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import Field

from schemas.common import OpenModel, StrictModel


class GetLogisticsByOrderNoArgs(StrictModel):
    order_no: str = Field(..., min_length=1, max_length=64)
    include_eta: bool = True


class LogisticsByOrderResult(OpenModel):
    orderId: str = ""
    orderNo: str = ""
    packages: List[Any] = Field(default_factory=list)


class GetLogisticsTrackingArgs(StrictModel):
    tracking_no: str = Field(..., min_length=1, max_length=64)
    express_company_code: Optional[str] = Field(default=None, max_length=32)
    include_eta: bool = True


class LogisticsTrackingResult(OpenModel):
    trackingNo: Optional[str] = None
    expressCompany: Optional[str] = None
    status: Optional[str] = None
    orderId: Optional[str] = None
    orderNo: Optional[str] = None
