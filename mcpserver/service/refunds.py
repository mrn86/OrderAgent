from __future__ import annotations

from typing import Any, Optional

from data import fake_data


def list_refunds(
    *,
    order_id: Optional[str] = None,
    order_no: Optional[str] = None,
    refund_id: Optional[str] = None,
    after_sale_id: Optional[str] = None,
    status: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    statuses = {s.strip() for s in status.split(",")} if status else set()
    rows = fake_data.all_refunds()
    filtered = []
    for item in rows:
        if order_id and item["orderId"] != order_id:
            continue
        if order_no and item["orderNo"] != order_no:
            continue
        if refund_id and item["refundId"] != refund_id:
            continue
        if after_sale_id and item["afterSaleId"] != after_sale_id:
            continue
        if statuses and item["status"] not in statuses:
            continue
        if created_from and item["appliedAt"] < created_from:
            continue
        if created_to and item["appliedAt"] > created_to:
            continue
        filtered.append(
            {
                "refundId": item["refundId"],
                "afterSaleId": item["afterSaleId"],
                "orderId": item["orderId"],
                "orderNo": item["orderNo"],
                "type": item["type"],
                "typeText": item["typeText"],
                "status": item["status"],
                "statusText": item["statusText"],
                "refundAmount": item["refundAmount"],
                "currency": item["currency"],
                "payChannel": item["payChannel"],
                "payChannelText": item["payChannelText"],
                "reasonCode": item["reasonCode"],
                "reasonText": item["reasonText"],
                "appliedAt": item["appliedAt"],
                "updatedAt": item.get("updatedAt"),
                "expectArriveAt": item.get("expectArriveAt"),
                "arrivedAt": item.get("arrivedAt"),
            }
        )

    total = len(filtered)
    start = max(page - 1, 0) * page_size
    end = start + page_size
    return {
        "list": filtered[start:end],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "hasMore": end < total,
    }


def get_refund_detail(refund_id: str) -> dict[str, Any]:
    item = fake_data.get_refund(refund_id)
    if not item:
        return {"error": {"code": 41003, "message": "退款单不存在或无权访问"}}
    return item


def get_progress(*, order_id: Optional[str] = None, order_no: Optional[str] = None) -> dict[str, Any]:
    if not order_id and not order_no:
        return {"error": {"code": 400, "message": "orderId 与 orderNo 二选一必填"}}

    rows = [
        i
        for i in fake_data.all_refunds()
        if (order_id and i["orderId"] == order_id) or (order_no and i["orderNo"] == order_no)
    ]
    if not rows:
        return {"error": {"code": 41008, "message": "订单无退款记录"}}

    first = rows[0]
    return {
        "orderId": first["orderId"],
        "orderNo": first["orderNo"],
        "hasRefund": True,
        "totalRefundAmount": sum(i["refundAmount"] for i in rows),
        "currency": first["currency"],
        "items": [
            {
                "refundId": i["refundId"],
                "type": i["type"],
                "status": i["status"],
                "statusText": i["statusText"],
                "refundAmount": i["refundAmount"],
                "currentStep": i["progress"]["currentStep"],
                "currentStepText": next(
                    (
                        s["stepText"]
                        for s in i["progress"]["steps"]
                        if s["step"] == i["progress"]["currentStep"]
                    ),
                    i["progress"]["currentStep"],
                ),
                "percent": i["progress"]["percent"],
                "summary": f"退款状态：{i['statusText']}",
                "expectArriveAt": i.get("expectArriveAt"),
                "arrivedAt": i.get("arrivedAt"),
            }
            for i in rows
        ],
    }


def create_refund(
    *,
    order_id: Optional[str] = None,
    order_no: Optional[str] = None,
    amount: int,
    reason: str,
    after_sale_id: Optional[str] = None,
) -> dict[str, Any]:
    """发起仅退款申请。amount 单位为分。"""
    return fake_data.create_refund(
        order_id=order_id,
        order_no=order_no,
        amount=amount,
        reason=reason,
        after_sale_id=after_sale_id,
    )
