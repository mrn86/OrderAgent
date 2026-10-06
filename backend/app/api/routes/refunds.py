from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import require_auth
from app.core.response import fail, ok
from app.service import refunds as refund_service

router = APIRouter(dependencies=[Depends(require_auth)])


class CreateRefundBody(BaseModel):
    orderId: Optional[str] = None
    orderNo: Optional[str] = None
    amount: int = Field(..., gt=0, description="退款金额，单位：分")
    reason: str = Field(..., min_length=4, max_length=200)
    afterSaleId: Optional[str] = None


@router.get("/refunds")
def list_refunds(
    orderId: Optional[str] = None,
    orderNo: Optional[str] = None,
    refundId: Optional[str] = None,
    afterSaleId: Optional[str] = None,
    status: Optional[str] = None,
    createdFrom: Optional[str] = None,
    createdTo: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=10, ge=1, le=50),
):
    data = refund_service.list_refunds(
        order_id=orderId,
        order_no=orderNo,
        refund_id=refundId,
        after_sale_id=afterSaleId,
        status=status,
        created_from=createdFrom,
        created_to=createdTo,
        page=page,
        page_size=pageSize,
    )
    return ok(data)


@router.get("/refunds/progress")
def refund_progress(orderId: Optional[str] = None, orderNo: Optional[str] = None):
    data = refund_service.get_progress(order_id=orderId, order_no=orderNo)
    if "error" in data:
        err = data["error"]
        return fail(err["code"], err["message"])
    return ok(data)


@router.post("/refunds")
def create_refund(body: CreateRefundBody):
    data = refund_service.create_refund(
        order_id=body.orderId,
        order_no=body.orderNo,
        amount=body.amount,
        reason=body.reason,
        after_sale_id=body.afterSaleId,
    )
    if "error" in data:
        err = data["error"]
        return fail(err["code"], err["message"])
    return ok(data)


@router.get("/refunds/{refundId}")
def get_refund(refundId: str):
    data = refund_service.get_refund_detail(refundId)
    if "error" in data:
        err = data["error"]
        return fail(err["code"], err["message"])
    return ok(data)
