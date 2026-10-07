from __future__ import annotations

from typing import Any, Optional

from app.service import fake_data
from app.core.database.redis_client import cache_get, cache_set


def _to_list_item(order: dict[str, Any]) -> dict[str, Any]:
    amounts = order.get("amounts") or {}
    return {
        "orderId": order["orderId"],
        "orderNo": order["orderNo"],
        "status": order["status"],
        "statusText": order["statusText"],
        "createdAt": order["createdAt"],
        "paidAt": order.get("paidAt"),
        "payAmount": amounts.get("payAmount", order.get("payAmount")),
        "goodsAmount": amounts.get("goodsAmount"),
        "freightAmount": amounts.get("freightAmount"),
        "discountAmount": amounts.get("discountAmount"),
        "currency": amounts.get("currency", "CNY"),
        "itemCount": len(order.get("items") or []),
        "items": [
            {
                "skuId": i.get("skuId"),
                "spuId": i.get("spuId"),
                "spuName": i.get("spuName"),
                "skuAttrs": i.get("skuAttrs"),
                "quantity": i.get("quantity"),
                "unitPrice": i.get("unitPrice"),
                "payPrice": i.get("payPrice"),
                "imageUrl": i.get("imageUrl"),
            }
            for i in order.get("items") or []
        ],
        "receiver": {
            "nameMask": order["receiver"]["nameMask"],
            "mobileMask": order["receiver"]["mobileMask"],
            "addressMask": order["receiver"]["addressMask"],
        },
        "logisticsSummary": {
            "expressCompany": (order.get("logisticsSummary") or {}).get("expressCompany"),
            "trackingNo": (order.get("logisticsSummary") or {}).get("trackingNo"),
            "latestTrace": (order.get("logisticsSummary") or {}).get("latestTrace"),
            "latestTraceAt": (order.get("logisticsSummary") or {}).get("latestTraceAt"),
            "eta": (order.get("logisticsSummary") or {}).get("eta"),
        },
        "afterSaleSummary": {
            "hasAfterSale": (order.get("afterSaleSummary") or {}).get("hasAfterSale", False),
            "activeCount": (order.get("afterSaleSummary") or {}).get("activeCount", 0),
        },
        "invoiceSummary": {
            "invoiced": (order.get("invoiceSummary") or {}).get("invoiced", False),
            "eligible": (order.get("invoiceSummary") or {}).get("eligible", False),
        },
    }


def list_orders(
    *,
    order_no: Optional[str] = None,
    order_id: Optional[str] = None,
    status: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    if created_from and created_to and created_from > created_to:
        return {"error": {"code": 20001, "message": "查询参数非法（时间范围颠倒）"}}

    statuses = {s.strip() for s in status.split(",")} if status else set()
    rows = fake_data.all_orders()
    filtered: list[dict[str, Any]] = []
    for order in rows:
        if order_no and order["orderNo"] != order_no:
            continue
        if order_id and order["orderId"] != order_id:
            continue
        if statuses and order["status"] not in statuses:
            continue
        if created_from and order["createdAt"] < created_from:
            continue
        if created_to and order["createdAt"] > created_to:
            continue
        if keyword:
            text = " ".join(
                [order["orderNo"], order["orderId"]]
                + [i.get("spuName", "") for i in order.get("items") or []]
            )
            if keyword not in text:
                continue
        filtered.append(order)

    if not filtered and (order_no or order_id or keyword or status):
        return {"error": {"code": 20002, "message": "未找到匹配订单"}}

    total = len(filtered)
    start = max(page - 1, 0) * page_size
    end = start + page_size
    page_rows = filtered[start:end]
    return {
        "list": [_to_list_item(o) for o in page_rows],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "hasMore": end < total,
    }


def get_order_detail(
    order_id: Optional[str] = None,
    order_no: Optional[str] = None,
    *,
    include_logistics: bool = True,
    include_after_sale: bool = True,
    include_invoice: bool = True,
) -> dict[str, Any]:
    cache_key = f"order:{order_id or order_no}:{include_logistics}:{include_after_sale}:{include_invoice}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    if order_id:
        order = fake_data.get_order_by_id(order_id)
    elif order_no:
        if not order_no.isdigit() and not order_no.startswith("20"):
            # keep format soft; only reject empty
            pass
        order = fake_data.get_order_by_no(order_no)
    else:
        return {"error": {"code": 400, "message": "缺少 orderId/orderNo"}}

    if not order:
        return {"error": {"code": 20010, "message": "订单不存在"}}

    data = dict(order)
    if not include_logistics:
        data.pop("logisticsSummary", None)
    if not include_after_sale:
        data.pop("afterSaleSummary", None)
    if not include_invoice:
        data.pop("invoiceSummary", None)

    cache_set(cache_key, data, ttl_seconds=60)
    return data
