from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_auth
from app.core.response import fail, ok
from app.service import orders as order_service

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/orders")
def list_orders(
    orderNo: Optional[str] = None,
    orderId: Optional[str] = None,
    status: Optional[str] = None,
    createdFrom: Optional[str] = None,
    createdTo: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=10, ge=1, le=50),
):
    data = order_service.list_orders(
        order_no=orderNo,
        order_id=orderId,
        status=status,
        created_from=createdFrom,
        created_to=createdTo,
        keyword=keyword,
        page=page,
        page_size=pageSize,
    )
    if "error" in data:
        err = data["error"]
        return fail(err["code"], err["message"])
    return ok(data)


@router.get("/orders/by-no/{orderNo}")
def get_order_by_no(
    orderNo: str,
    includeLogistics: bool = True,
    includeAfterSale: bool = True,
    includeInvoice: bool = True,
):
    data = order_service.get_order_detail(
        order_no=orderNo,
        include_logistics=includeLogistics,
        include_after_sale=includeAfterSale,
        include_invoice=includeInvoice,
    )
    if "error" in data:
        err = data["error"]
        return fail(err["code"], err["message"])
    return ok(data)


@router.get("/orders/{orderId}")
def get_order(
    orderId: str,
    includeLogistics: bool = True,
    includeAfterSale: bool = True,
    includeInvoice: bool = True,
):
    data = order_service.get_order_detail(
        order_id=orderId,
        include_logistics=includeLogistics,
        include_after_sale=includeAfterSale,
        include_invoice=includeInvoice,
    )
    if "error" in data:
        err = data["error"]
        return fail(err["code"], err["message"])
    return ok(data)
