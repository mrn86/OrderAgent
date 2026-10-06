"""In-memory fake dataset aligned with docs/api.md examples."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

ORDER = {
    "orderId": "O20260920001",
    "orderNo": "2026092012345678",
    "status": "SHIPPING",
    "statusText": "运输中",
    "createdAt": "2026-09-23T14:22:10+08:00",
    "paidAt": "2026-09-23T14:23:01+08:00",
    "shippedAt": "2026-09-24T10:00:00+08:00",
    "completedAt": None,
    "cancelledAt": None,
    "buyer": {"userId": "U10086", "nicknameMask": "宁*"},
    "amounts": {
        "goodsAmount": 32900,
        "freightAmount": 0,
        "discountAmount": 3000,
        "payAmount": 29900,
        "currency": "CNY",
    },
    "payment": {
        "payChannel": "WECHAT",
        "payChannelText": "微信支付",
        "transactionNo": "420000xxxxxxx",
        "paidAt": "2026-09-23T14:23:01+08:00",
    },
    "items": [
        {
            "orderItemId": "OI-1",
            "skuId": "SKU-8899",
            "spuId": "SPU-1001",
            "spuName": "轻跑运动鞋",
            "skuAttrs": "红色 / 42码",
            "quantity": 1,
            "unitPrice": 32900,
            "payPrice": 29900,
            "imageUrl": "https://cdn.example.com/sku/8899.jpg",
            "afterSaleStatus": None,
        }
    ],
    "receiver": {
        "nameMask": "张*",
        "mobileMask": "138****0000",
        "province": "上海市",
        "city": "上海市",
        "district": "浦东新区",
        "addressMask": "世纪大道****",
    },
    "merchant": {"merchantId": "M10001", "merchantName": "运动旗舰店"},
    "logisticsSummary": {
        "packageCount": 1,
        "expressCompany": "顺丰速运",
        "trackingNo": "SF1234567890",
        "status": "IN_TRANSIT",
        "statusText": "运输中",
        "latestTrace": "快件已到达【上海转运中心】",
        "latestTraceAt": "2026-09-28T21:10:00+08:00",
        "eta": {
            "predictArriveAt": "2026-09-29T18:00:00+08:00",
            "predictArriveWindow": {
                "earliest": "2026-09-29T14:00:00+08:00",
                "latest": "2026-09-29T20:00:00+08:00",
            },
            "confidence": 0.86,
            "delayRisk": "LOW",
            "isOverdue": False,
        },
    },
    "afterSaleSummary": {
        "hasAfterSale": True,
        "activeCount": 1,
        "latestAfterSaleId": "AS20260925001",
    },
    "invoiceSummary": {
        "eligible": True,
        "invoiced": True,
        "invoiceId": "INV20260929001",
        "status": "ISSUED",
    },
    "remark": {"buyerRemark": "尽量工作日派送", "merchantRemark": None},
}

ORDER_2 = {
    "orderId": "O20260915008",
    "orderNo": "2026091508765432",
    "status": "COMPLETED",
    "statusText": "交易完成",
    "createdAt": "2026-09-15T10:00:00+08:00",
    "paidAt": "2026-09-15T10:01:00+08:00",
    "shippedAt": "2026-09-16T09:00:00+08:00",
    "completedAt": "2026-09-18T16:00:00+08:00",
    "cancelledAt": None,
    "buyer": {"userId": "U10086", "nicknameMask": "宁*"},
    "amounts": {
        "goodsAmount": 45900,
        "freightAmount": 0,
        "discountAmount": 0,
        "payAmount": 45900,
        "currency": "CNY",
    },
    "payment": {
        "payChannel": "ALIPAY",
        "payChannelText": "支付宝",
        "transactionNo": "20260915xxxxxxx",
        "paidAt": "2026-09-15T10:01:00+08:00",
    },
    "items": [
        {
            "orderItemId": "OI-2",
            "skuId": "SKU-6601",
            "spuId": "SPU-2002",
            "spuName": "篮球鞋",
            "skuAttrs": "黑色 / 43码",
            "quantity": 1,
            "unitPrice": 45900,
            "payPrice": 45900,
            "imageUrl": "https://cdn.example.com/sku/6601.jpg",
            "afterSaleStatus": None,
        }
    ],
    "receiver": {
        "nameMask": "张*",
        "mobileMask": "138****0000",
        "province": "上海市",
        "city": "上海市",
        "district": "浦东新区",
        "addressMask": "世纪大道****",
    },
    "merchant": {"merchantId": "M10001", "merchantName": "运动旗舰店"},
    "logisticsSummary": {
        "packageCount": 1,
        "expressCompany": "圆通速递",
        "trackingNo": "YT9988776655",
        "status": "SIGNED",
        "statusText": "已签收",
        "latestTrace": "快件已签收",
        "latestTraceAt": "2026-09-18T15:30:00+08:00",
        "eta": None,
    },
    "afterSaleSummary": {"hasAfterSale": False, "activeCount": 0, "latestAfterSaleId": None},
    "invoiceSummary": {
        "eligible": True,
        "invoiced": False,
        "invoiceId": None,
        "status": None,
    },
    "remark": {"buyerRemark": None, "merchantRemark": None},
}

LOGISTICS = {
    "orderId": "O20260920001",
    "orderNo": "2026092012345678",
    "packages": [
        {
            "packageId": "PKG-1",
            "expressCompany": "顺丰速运",
            "expressCompanyCode": "SF",
            "trackingNo": "SF1234567890",
            "status": "IN_TRANSIT",
            "statusText": "运输中",
            "shippedAt": "2026-09-24T10:00:00+08:00",
            "signedAt": None,
            "receiver": {
                "nameMask": "张*",
                "mobileMask": "138****0000",
                "addressMask": "上海市浦东新区****",
            },
            "traces": [
                {
                    "time": "2026-09-28T21:10:00+08:00",
                    "desc": "快件已到达【上海转运中心】",
                    "city": "上海",
                    "status": "IN_TRANSIT",
                },
                {
                    "time": "2026-09-24T10:05:00+08:00",
                    "desc": "快件已由【杭州萧山集货仓】揽收",
                    "city": "杭州",
                    "status": "PICKED_UP",
                },
            ],
            "eta": {
                "predictArriveAt": "2026-09-29T18:00:00+08:00",
                "predictArriveWindow": {
                    "earliest": "2026-09-29T14:00:00+08:00",
                    "latest": "2026-09-29T20:00:00+08:00",
                },
                "confidence": 0.86,
                "delayRisk": "LOW",
                "delayReason": None,
                "promisedArriveAt": "2026-09-30T23:59:59+08:00",
                "isOverdue": False,
                "updatedAt": "2026-09-29T08:00:00+08:00",
            },
        }
    ],
}

AFTER_SALE = {
    "afterSaleId": "AS20260925001",
    "orderId": "O20260920001",
    "orderNo": "2026092012345678",
    "type": "RETURN",
    "typeText": "退货退款",
    "status": "RETURNING",
    "statusText": "退货寄回中",
    "reasonCode": "QUALITY",
    "reasonText": "商品质量问题",
    "applyAmount": 29900,
    "refundAmount": None,
    "currency": "CNY",
    "createdAt": "2026-09-25T11:00:00+08:00",
    "updatedAt": "2026-09-26T09:30:00+08:00",
    "items": [
        {
            "orderItemId": "OI-1",
            "skuId": "SKU-8899",
            "spuName": "轻跑运动鞋",
            "quantity": 1,
        }
    ],
    "progress": {
        "currentStep": "BUYER_SHIPPED",
        "percent": 60,
        "steps": [
            {
                "step": "APPLIED",
                "stepText": "提交申请",
                "status": "DONE",
                "time": "2026-09-25T11:00:00+08:00",
                "desc": "已提交退货退款申请",
            },
            {
                "step": "MERCHANT_APPROVED",
                "stepText": "商家审核",
                "status": "DONE",
                "time": "2026-09-25T15:20:00+08:00",
                "desc": "商家已同意，请寄回商品",
            },
            {
                "step": "BUYER_SHIPPED",
                "stepText": "买家寄回",
                "status": "ACTIVE",
                "time": "2026-09-26T09:30:00+08:00",
                "desc": "退货已揽收，运单 SF99887766",
            },
            {
                "step": "WAREHOUSE_RECEIVED",
                "stepText": "仓库签收验货",
                "status": "PENDING",
                "time": None,
                "desc": None,
            },
            {
                "step": "REFUND_PROCESSING",
                "stepText": "退款处理",
                "status": "PENDING",
                "time": None,
                "desc": None,
            },
            {
                "step": "COMPLETED",
                "stepText": "完成",
                "status": "PENDING",
                "time": None,
                "desc": None,
            },
        ],
    },
    "returnLogistics": {
        "expressCompany": "顺丰速运",
        "trackingNo": "SF99887766",
        "latestTrace": "快件运输中",
    },
    "refund": {
        "refundId": None,
        "refundAmount": None,
        "refundStatus": "NOT_STARTED",
        "refundChannel": None,
        "refundArriveAt": None,
        "refundArriveExpectAt": None,
    },
    "sla": {
        "nextActionOwner": "WAREHOUSE",
        "nextActionText": "等待仓库签收验货",
        "expectFinishAt": "2026-09-30T18:00:00+08:00",
    },
    "timeline": [
        {
            "time": "2026-09-26T09:30:00+08:00",
            "event": "BUYER_SHIPPED",
            "title": "买家已寄出",
            "detail": "运单号 SF99887766",
        }
    ],
    "rejectInfo": None,
}

REFUND = {
    "refundId": "RF20260929001",
    "afterSaleId": "AS20260929010",
    "orderId": "O20260920001",
    "orderNo": "2026092012345678",
    "type": "REFUND_ONLY",
    "typeText": "仅退款",
    "status": "SUCCESS",
    "statusText": "退款成功",
    "refundAmount": 29900,
    "currency": "CNY",
    "payChannel": "WECHAT",
    "payChannelText": "原路退回微信",
    "transactionNo": "5020260929xxxxxxx",
    "reasonCode": "NOT_WANT",
    "reasonText": "不想要了",
    "remark": "未发货，申请仅退款",
    "items": [
        {
            "orderItemId": "OI-1",
            "skuId": "SKU-8899",
            "spuName": "轻跑运动鞋",
            "quantity": 1,
            "refundAmount": 29900,
        }
    ],
    "progress": {
        "currentStep": "ARRIVED",
        "percent": 100,
        "steps": [
            {
                "step": "APPLIED",
                "stepText": "提交申请",
                "status": "DONE",
                "time": "2026-09-29T11:00:00+08:00",
                "desc": "已提交仅退款申请",
            },
            {
                "step": "MERCHANT_APPROVED",
                "stepText": "商家审核",
                "status": "DONE",
                "time": "2026-09-29T11:02:00+08:00",
                "desc": "商家已同意退款",
            },
            {
                "step": "REFUNDING",
                "stepText": "退款执行中",
                "status": "DONE",
                "time": "2026-09-29T11:03:00+08:00",
                "desc": "已发起支付渠道退款",
            },
            {
                "step": "ARRIVED",
                "stepText": "到账完成",
                "status": "DONE",
                "time": "2026-09-29T11:18:00+08:00",
                "desc": "退款已原路退回微信",
            },
        ],
    },
    "appliedAt": "2026-09-29T11:00:00+08:00",
    "approvedAt": "2026-09-29T11:02:00+08:00",
    "refundingAt": "2026-09-29T11:03:00+08:00",
    "expectArriveAt": "2026-09-30T11:00:00+08:00",
    "arrivedAt": "2026-09-29T11:18:00+08:00",
    "failReason": None,
    "updatedAt": "2026-09-29T11:18:00+08:00",
}

INVOICE = {
    "invoiceId": "INV20260929001",
    "applicationNo": "IA20260929001",
    "orderId": "O20260920001",
    "orderNo": "2026092012345678",
    "status": "ISSUED",
    "statusText": "已开票",
    "invoiceType": "ELECTRONIC_NORMAL",
    "invoiceTypeText": "电子普通发票",
    "amount": 29900,
    "currency": "CNY",
    "title": {
        "titleType": "ENTERPRISE",
        "titleName": "某某科技有限公司",
        "taxNo": "91310000MA1XXXXXX",
        "email": "finance@example.com",
    },
    "invoiceCode": "04400xxxxxx",
    "invoiceNumber": "12345678",
    "checkCode": "12345678901234567890",
    "issuedAt": "2026-09-29T10:18:00+08:00",
    "buyer": {"name": "某某科技有限公司", "taxNo": "91310000MA1XXXXXX"},
    "seller": {"name": "运动旗舰店所属主体", "taxNo": "91310000MA2XXXXXX"},
    "lineItems": [
        {
            "name": "轻跑运动鞋",
            "spec": "红色 / 42码",
            "unit": "件",
            "quantity": "1",
            "unitPrice": 29900,
            "amount": 29900,
            "taxRate": "0.13",
            "taxAmount": 3439,
        }
    ],
    "files": [
        {
            "type": "PDF",
            "url": "https://cdn.example.com/inv/INV20260929001.pdf?sign=xxx",
            "expireAt": "2026-09-29T11:18:00+08:00",
            "sizeBytes": 102400,
        },
        {
            "type": "OFD",
            "url": "https://cdn.example.com/inv/INV20260929001.ofd?sign=xxx",
            "expireAt": "2026-09-29T11:18:00+08:00",
            "sizeBytes": 89600,
        },
    ],
    "progress": {
        "currentStep": "ISSUED",
        "steps": [
            {
                "step": "SUBMITTED",
                "stepText": "已提交",
                "status": "DONE",
                "time": "2026-09-29T10:00:00+08:00",
            },
            {
                "step": "PROCESSING",
                "stepText": "税控开具中",
                "status": "DONE",
                "time": "2026-09-29T10:10:00+08:00",
            },
            {
                "step": "ISSUED",
                "stepText": "已开具",
                "status": "DONE",
                "time": "2026-09-29T10:18:00+08:00",
            },
            {
                "step": "PUSHED",
                "stepText": "已发送邮箱",
                "status": "DONE",
                "time": "2026-09-29T10:18:05+08:00",
            },
        ],
    },
    "failReason": None,
}


def _clone(obj: Any) -> Any:
    return deepcopy(obj)


def all_orders() -> list[dict[str, Any]]:
    return [_clone(ORDER), _clone(ORDER_2)]


def get_order_by_id(order_id: str) -> dict[str, Any] | None:
    for o in all_orders():
        if o["orderId"] == order_id:
            return o
    return None


def get_order_by_no(order_no: str) -> dict[str, Any] | None:
    for o in all_orders():
        if o["orderNo"] == order_no:
            return o
    return None


def get_logistics_by_order_no(order_no: str) -> dict[str, Any] | None:
    if LOGISTICS["orderNo"] == order_no:
        return _clone(LOGISTICS)
    order = get_order_by_no(order_no)
    if not order:
        return None
    summary = order.get("logisticsSummary") or {}
    return {
        "orderId": order["orderId"],
        "orderNo": order["orderNo"],
        "packages": [
            {
                "packageId": "PKG-1",
                "expressCompany": summary.get("expressCompany"),
                "expressCompanyCode": "YTO",
                "trackingNo": summary.get("trackingNo"),
                "status": summary.get("status"),
                "statusText": summary.get("statusText"),
                "shippedAt": order.get("shippedAt"),
                "signedAt": order.get("completedAt"),
                "receiver": {
                    "nameMask": order["receiver"]["nameMask"],
                    "mobileMask": order["receiver"]["mobileMask"],
                    "addressMask": order["receiver"]["addressMask"],
                },
                "traces": [
                    {
                        "time": summary.get("latestTraceAt"),
                        "desc": summary.get("latestTrace"),
                        "city": "上海",
                        "status": summary.get("status"),
                    }
                ],
                "eta": summary.get("eta"),
            }
        ],
    }


def get_tracking(tracking_no: str, company_code: str | None = None) -> dict[str, Any] | None:
    for pkg in LOGISTICS["packages"]:
        if pkg["trackingNo"] == tracking_no:
            if company_code and pkg["expressCompanyCode"] != company_code:
                return None
            data = _clone(pkg)
            data["orderId"] = LOGISTICS["orderId"]
            data["orderNo"] = LOGISTICS["orderNo"]
            return data
    for order in all_orders():
        summary = order.get("logisticsSummary") or {}
        if summary.get("trackingNo") == tracking_no:
            return {
                "orderId": order["orderId"],
                "orderNo": order["orderNo"],
                "packageId": "PKG-1",
                "expressCompany": summary.get("expressCompany"),
                "expressCompanyCode": company_code or "YTO",
                "trackingNo": tracking_no,
                "status": summary.get("status"),
                "statusText": summary.get("statusText"),
                "shippedAt": order.get("shippedAt"),
                "signedAt": order.get("completedAt"),
                "traces": [
                    {
                        "time": summary.get("latestTraceAt"),
                        "desc": summary.get("latestTrace"),
                        "city": "上海",
                        "status": summary.get("status"),
                    }
                ],
                "eta": summary.get("eta"),
            }
    return None


def all_after_sales() -> list[dict[str, Any]]:
    return [_clone(AFTER_SALE)]


def get_after_sale(after_sale_id: str) -> dict[str, Any] | None:
    for item in all_after_sales():
        if item["afterSaleId"] == after_sale_id:
            return item
    return None


def all_refunds() -> list[dict[str, Any]]:
    return [_clone(REFUND)] + [_clone(item) for item in _CREATED_REFUNDS]


def get_refund(refund_id: str) -> dict[str, Any] | None:
    for item in all_refunds():
        if item["refundId"] == refund_id:
            return item
    return None


# 运行期新建的退款单（内存）；与静态 REFUND 一并参与查询
_CREATED_REFUNDS: list[dict[str, Any]] = []
_REFUND_SEQ = 0

# 允许发起退款的订单状态
_REFUNDABLE_STATUSES = frozenset({"PAID", "SHIPPING", "COMPLETED", "DELIVERED"})


def create_refund(
    *,
    order_id: str | None = None,
    order_no: str | None = None,
    amount: int,
    reason: str,
    after_sale_id: str | None = None,
) -> dict[str, Any]:
    """创建仅退款申请；同订单+金额+原因幂等返回已有单。"""
    global _REFUND_SEQ

    if not order_id and not order_no:
        return {"error": {"code": 400, "message": "orderId 与 orderNo 二选一必填"}}
    if amount <= 0:
        return {"error": {"code": 400, "message": "退款金额必须大于 0（单位：分）"}}

    order = get_order_by_id(order_id) if order_id else get_order_by_no(order_no or "")
    if not order:
        return {"error": {"code": 40001, "message": "订单不存在或无权访问"}}

    if order["status"] not in _REFUNDABLE_STATUSES:
        return {
            "error": {
                "code": 41010,
                "message": f"订单当前状态 {order.get('statusText') or order['status']} 不可退款",
            }
        }

    pay_amount = int(order.get("amounts", {}).get("payAmount") or 0)
    if amount > pay_amount:
        return {
            "error": {
                "code": 41011,
                "message": f"退款金额超过可退金额（可退 {pay_amount} 分）",
            }
        }

    reason_text = (reason or "").strip()
    # 幂等：同一订单 + 金额 + 原因已有处理中/成功单则直接返回
    for existing in all_refunds():
        if (
            existing["orderId"] == order["orderId"]
            and int(existing["refundAmount"]) == amount
            and existing.get("reasonText") == reason_text
            and existing["status"] in {"PROCESSING", "SUCCESS", "APPLIED", "APPROVED"}
        ):
            return existing

    _REFUND_SEQ += 1
    now = "2026-09-30T12:00:00+08:00"
    refund_id = f"RF20260930{_REFUND_SEQ:03d}"
    after_id = after_sale_id or f"AS{refund_id[2:]}"
    payment = order.get("payment") or {}
    pay_channel = payment.get("payChannel") or "WECHAT"
    pay_channel_text = {
        "WECHAT": "原路退回微信",
        "ALIPAY": "原路退回支付宝",
    }.get(pay_channel, f"原路退回{pay_channel}")

    items = []
    for item in order.get("items") or []:
        items.append(
            {
                "orderItemId": item.get("orderItemId"),
                "skuId": item.get("skuId"),
                "spuName": item.get("spuName"),
                "quantity": item.get("quantity"),
                "refundAmount": amount if len(order.get("items") or []) == 1 else item.get("payPrice"),
            }
        )
    if not items:
        items = [{"orderItemId": None, "skuId": None, "spuName": None, "quantity": 1, "refundAmount": amount}]

    created = {
        "refundId": refund_id,
        "afterSaleId": after_id,
        "orderId": order["orderId"],
        "orderNo": order["orderNo"],
        "type": "REFUND_ONLY",
        "typeText": "仅退款",
        "status": "PROCESSING",
        "statusText": "退款处理中",
        "refundAmount": amount,
        "currency": order.get("amounts", {}).get("currency") or "CNY",
        "payChannel": pay_channel,
        "payChannelText": pay_channel_text,
        "transactionNo": None,
        "reasonCode": "USER_REQUEST",
        "reasonText": reason_text,
        "remark": reason_text,
        "items": items,
        "progress": {
            "currentStep": "APPLIED",
            "percent": 25,
            "steps": [
                {
                    "step": "APPLIED",
                    "stepText": "提交申请",
                    "status": "DONE",
                    "time": now,
                    "desc": "已提交仅退款申请",
                },
                {
                    "step": "MERCHANT_APPROVED",
                    "stepText": "商家审核",
                    "status": "PENDING",
                    "time": None,
                    "desc": "等待商家审核",
                },
                {
                    "step": "REFUNDING",
                    "stepText": "退款执行中",
                    "status": "PENDING",
                    "time": None,
                    "desc": "待发起支付渠道退款",
                },
                {
                    "step": "ARRIVED",
                    "stepText": "到账完成",
                    "status": "PENDING",
                    "time": None,
                    "desc": "待原路退回",
                },
            ],
        },
        "appliedAt": now,
        "approvedAt": None,
        "refundingAt": None,
        "expectArriveAt": "2026-10-01T12:00:00+08:00",
        "arrivedAt": None,
        "failReason": None,
        "updatedAt": now,
    }
    _CREATED_REFUNDS.append(created)
    return _clone(created)


def all_invoices() -> list[dict[str, Any]]:
    return [_clone(INVOICE)]


def get_invoice(invoice_id: str) -> dict[str, Any] | None:
    for item in all_invoices():
        if item["invoiceId"] == invoice_id:
            return item
    return None
