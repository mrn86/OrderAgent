from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import require_auth
from app.core.response import fail, ok
from app.service import invoices as invoice_service

router = APIRouter(dependencies=[Depends(require_auth)])


class DownloadUrlRequest(BaseModel):
    types: Optional[List[str]] = Field(default=None)
    expireSeconds: int = Field(default=1800, ge=900, le=3600)


@router.get("/invoices")
def list_invoices(
    orderId: Optional[str] = None,
    orderNo: Optional[str] = None,
    status: Optional[str] = None,
    invoiceType: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=10, ge=1, le=50),
):
    data = invoice_service.list_by_order(
        order_id=orderId,
        order_no=orderNo,
        status=status,
        invoice_type=invoiceType,
        page=page,
        page_size=pageSize,
    )
    if "error" in data:
        err = data["error"]
        return fail(err["code"], err["message"])
    return ok(data)


@router.get("/invoices/{invoiceId}")
def get_invoice(
    invoiceId: str,
    includeFiles: bool = True,
    includeProgress: bool = True,
):
    data = invoice_service.get_invoice(
        invoiceId,
        include_files=includeFiles,
        include_progress=includeProgress,
    )
    if "error" in data:
        err = data["error"]
        return fail(err["code"], err["message"])
    return ok(data)


@router.post("/invoices/{invoiceId}/download-urls")
def download_urls(invoiceId: str, body: DownloadUrlRequest):
    data = invoice_service.create_download_urls(
        invoiceId,
        types=body.types,
        expire_seconds=body.expireSeconds,
    )
    if "error" in data:
        err = data["error"]
        return fail(err["code"], err["message"])
    return ok(data)
