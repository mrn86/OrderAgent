from __future__ import annotations

from typing import Any, Optional

from app.core import fake_data


def list_after_sales(
    *,
    order_id: Optional[str] = None,
    order_no: Optional[str] = None,
    after_sale_id: Optional[str] = None,
    type_: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    rows = fake_data.all_after_sales()
    filtered = []
    for item in rows:
        if order_id and item["orderId"] != order_id:
            continue
        if order_no and item["orderNo"] != order_no:
            continue
        if after_sale_id and item["afterSaleId"] != after_sale_id:
            continue
        if type_ and item["type"] != type_:
            continue
        if status and item["status"] != status:
            continue
        list_item = {k: v for k, v in item.items() if k not in {"timeline", "rejectInfo"}}
        filtered.append(list_item)

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


def get_after_sale_detail(after_sale_id: str) -> dict[str, Any]:
    item = fake_data.get_after_sale(after_sale_id)
    if not item:
        return {"error": {"code": 40001, "message": "售后单不存在或无权访问"}}
    return item


def get_progress(*, order_id: Optional[str] = None, order_no: Optional[str] = None) -> dict[str, Any]:
    if not order_id and not order_no:
        return {"error": {"code": 400, "message": "orderId 与 orderNo 二选一必填"}}

    rows = fake_data.all_after_sales()
    matched = [
        i
        for i in rows
        if (order_id and i["orderId"] == order_id) or (order_no and i["orderNo"] == order_no)
    ]
    if not matched:
        return {"error": {"code": 40002, "message": "订单无售后记录"}}

    first = matched[0]
    return {
        "orderId": first["orderId"],
        "orderNo": first["orderNo"],
        "hasAfterSale": True,
        "items": [
            {
                "afterSaleId": i["afterSaleId"],
                "type": i["type"],
                "typeText": i["typeText"],
                "status": i["status"],
                "statusText": i["statusText"],
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
                "summary": i["sla"]["nextActionText"],
                "expectFinishAt": i["sla"]["expectFinishAt"],
                "refundStatus": (i.get("refund") or {}).get("refundStatus"),
            }
            for i in matched
        ],
    }
