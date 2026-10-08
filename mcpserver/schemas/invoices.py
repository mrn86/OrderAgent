"""发票工具契约。"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import Field

from schemas.common import OpenModel, StrictModel


class GetInvoiceArgs(StrictModel):
    invoice_id: str = Field(..., min_length=1, max_length=64)


class InvoiceDetailResult(OpenModel):
    invoiceId: str
    orderId: str = ""
    orderNo: str = ""
    status: str = ""


class ListInvoicesByOrderArgs(StrictModel):
    order_no: Optional[str] = Field(default=None, max_length=64)
    order_id: Optional[str] = Field(default=None, max_length=64)


class ListInvoicesByOrderResult(OpenModel):
    orderId: Optional[str] = None
    orderNo: Optional[str] = None
    list: List[Any] = Field(default_factory=list)
    page: int = 1
    pageSize: int = 10
    total: int = 0
    hasMore: bool = False


class CreateInvoiceDownloadUrlsArgs(StrictModel):
    invoice_id: str = Field(..., min_length=1, max_length=64)
    types: str = Field(default="PDF,OFD", max_length=64)
    expire_seconds: int = Field(default=1800, ge=900, le=3600)


class InvoiceDownloadUrlsResult(OpenModel):
    invoiceId: str
    status: str = ""
    files: List[Any] = Field(default_factory=list)
