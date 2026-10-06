from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_auth
from app.core.response import fail, ok
from app.service import after_sales as after_sale_service

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/after-sales")
def list_after_sales(
    orderId: Optional[str] = None,
    orderNo: Optional[str] = None,
    afterSaleId: Optional[str] = None,
    type: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=10, ge=1, le=50),
):
    data = after_sale_service.list_after_sales(
        order_id=orderId,
        order_no=orderNo,
        after_sale_id=afterSaleId,
        type_=type,
        status=status,
        page=page,
        page_size=pageSize,
    )
    return ok(data)


@router.get("/after-sales/progress")
def after_sale_progress(orderId: Optional[str] = None, orderNo: Optional[str] = None):
    data = after_sale_service.get_progress(order_id=orderId, order_no=orderNo)
    if "error" in data:
        err = data["error"]
        return fail(err["code"], err["message"])
    return ok(data)


@router.get("/after-sales/{afterSaleId}")
def get_after_sale(afterSaleId: str):
    data = after_sale_service.get_after_sale_detail(afterSaleId)
    if "error" in data:
        err = data["error"]
        return fail(err["code"], err["message"])
    return ok(data)
