"""In-memory fake dataset aligned with docs/api.md examples."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
import json

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
    "buyer": {"userId": "U10086", "nicknameMask": "王*"},
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
    "afterSaleSummary": {
        "hasAfterSale": True,
        "activeCount": 0,
        "latestAfterSaleId": "AS20260918008",
    },
    "invoiceSummary": {
        "eligible": True,
        "invoiced": False,
        "invoiceId": None,
        "status": None,
    },
    "remark": {"buyerRemark": None, "merchantRemark": None},
}

# 额外假订单：待发货 / 运输中 / 已送达 / 交易完成。物流与退货样例挂在运输中那条上。
_ORDER_STATUS_CYCLE: list[tuple[str, str]] = [
    ("PAID", "待发货"),
    ("SHIPPING", "运输中"),
    ("DELIVERED", "已送达"),
    ("COMPLETED", "交易完成"),
    ("CANCELLED", "已取消"),
]

_EXTRA_PRODUCTS: list[dict[str, Any]] = [
    {"skuId": "SKU-7101", "spuId": "SPU-3001", "spuName": "运动短裤", "skuAttrs": "蓝色 / L", "unitPrice": 12900},
    {"skuId": "SKU-7102", "spuId": "SPU-3002", "spuName": "速干T恤", "skuAttrs": "白色 / M", "unitPrice": 9900},
    {"skuId": "SKU-7103", "spuId": "SPU-3003", "spuName": "跑步袜套装", "skuAttrs": "混色 / 均码", "unitPrice": 5900},
    {"skuId": "SKU-7104", "spuId": "SPU-3004", "spuName": "健身护腕", "skuAttrs": "黑色 / 一对", "unitPrice": 7900},
    {"skuId": "SKU-7105", "spuId": "SPU-3005", "spuName": "瑜伽垫", "skuAttrs": "紫色 / 6mm", "unitPrice": 15900},
    {"skuId": "SKU-7106", "spuId": "SPU-3006", "spuName": "运动水杯", "skuAttrs": "灰色 / 700ml", "unitPrice": 8900},
    {"skuId": "SKU-7107", "spuId": "SPU-3007", "spuName": "压缩裤", "skuAttrs": "黑色 / XL", "unitPrice": 19900},
    {"skuId": "SKU-7108", "spuId": "SPU-3008", "spuName": "羽毛球拍", "skuAttrs": "碳纤维 / 4U", "unitPrice": 28900},
    {"skuId": "SKU-7109", "spuId": "SPU-3009", "spuName": "网球", "skuAttrs": "黄色 / 3只装", "unitPrice": 6900},
    {"skuId": "SKU-7110", "spuId": "SPU-3010", "spuName": "泳镜", "skuAttrs": "透明 / 均码", "unitPrice": 11900},
    {"skuId": "SKU-7111", "spuId": "SPU-3011", "spuName": "登山杖", "skuAttrs": "银色 / 可调节", "unitPrice": 16900},
    {"skuId": "SKU-7112", "spuId": "SPU-3012", "spuName": "骑行手套", "skuAttrs": "红色 / M", "unitPrice": 8500},
    {"skuId": "SKU-7113", "spuId": "SPU-3013", "spuName": "运动腰包", "skuAttrs": "黑色 / 单袋", "unitPrice": 7500},
    {"skuId": "SKU-7114", "spuId": "SPU-3014", "spuName": "跳绳", "skuAttrs": "钢丝绳 / 可调", "unitPrice": 4500},
    {"skuId": "SKU-7115", "spuId": "SPU-3015", "spuName": "力量带", "skuAttrs": "中等阻力", "unitPrice": 6500},
    {"skuId": "SKU-7116", "spuId": "SPU-3016", "spuName": "篮球", "skuAttrs": "7号 / 室内", "unitPrice": 14900},
    {"skuId": "SKU-7117", "spuId": "SPU-3017", "spuName": "足球", "skuAttrs": "5号 / 训练", "unitPrice": 13900},
    {"skuId": "SKU-7118", "spuId": "SPU-3018", "spuName": "运动帽", "skuAttrs": "藏青色 / 均码", "unitPrice": 7900},
    {"skuId": "SKU-7119", "spuId": "SPU-3019", "spuName": "防晒袖套", "skuAttrs": "灰色 / 一对", "unitPrice": 4900},
    {"skuId": "SKU-7120", "spuId": "SPU-3020", "spuName": "运动毛巾", "skuAttrs": "白色 / 中号", "unitPrice": 3900},
    {"skuId": "SKU-7121", "spuId": "SPU-3021", "spuName": "护膝", "skuAttrs": "黑色 / L", "unitPrice": 10900},
    {"skuId": "SKU-7122", "spuId": "SPU-3022", "spuName": "哑铃套装", "skuAttrs": "2kg×2", "unitPrice": 21900},
    {"skuId": "SKU-7123", "spuId": "SPU-3023", "spuName": "泡沫轴", "skuAttrs": "蓝色 / 45cm", "unitPrice": 9900},
    {"skuId": "SKU-7124", "spuId": "SPU-3024", "spuName": "计步手环", "skuAttrs": "黑色 / 标准版", "unitPrice": 25900},
    {"skuId": "SKU-7125", "spuId": "SPU-3025", "spuName": "运动背包", "skuAttrs": "迷彩 / 20L", "unitPrice": 18900},
]

_EXTRA_CITIES: list[tuple[str, str, str, str]] = [
    ("上海市", "上海市", "浦东新区", "世纪大道****"),
    ("北京市", "北京市", "朝阳区", "建国路****"),
    ("广东省", "深圳市", "南山区", "科技园****"),
    ("浙江省", "杭州市", "西湖区", "文三路****"),
    ("江苏省", "南京市", "鼓楼区", "中山路****"),
]

_EXPRESS: list[tuple[str, str]] = [
    ("顺丰速运", "SF"),
    ("圆通速递", "YT"),
    ("中通快递", "ZT"),
    ("韵达快递", "YD"),
    ("京东物流", "JD"),
]


def _build_extra_orders(count: int = 25) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(count):
        status, status_text = _ORDER_STATUS_CYCLE[i % len(_ORDER_STATUS_CYCLE)]
        product = _EXTRA_PRODUCTS[i % len(_EXTRA_PRODUCTS)]
        province, city, district, address = _EXTRA_CITIES[i % len(_EXTRA_CITIES)]
        express_name, express_code = _EXPRESS[i % len(_EXPRESS)]
        day = 1 + (i % 28)
        seq = i + 1
        order_id = f"O202610{day:02d}{seq:03d}"
        order_no = f"202610{day:02d}{10000000 + seq}"
        created = f"2026-10-{day:02d}T10:{i % 60:02d}:00+08:00"
        # 已取消统一为「未付款取消」：无支付、实付 0；其余状态均有支付时间
        paid = (
            None
            if status == "CANCELLED"
            else f"2026-10-{day:02d}T10:{min(i % 60 + 1, 59):02d}:00+08:00"
        )
        qty = 1 + (i % 2)
        unit = int(product["unitPrice"])
        goods = unit * qty
        discount = 500 if i % 3 == 0 else 0
        freight = 0 if goods >= 9900 else 800
        pay = goods + freight - discount
        shipped = None
        completed = None
        cancelled = None
        logistics: dict[str, Any] | None
        after_sale = {"hasAfterSale": False, "activeCount": 0, "latestAfterSaleId": None}
        invoice = {"eligible": True, "invoiced": False, "invoiceId": None, "status": None}

        if status == "PAID":
            logistics = {
                "packageCount": 0,
                "expressCompany": None,
                "trackingNo": None,
                "status": "PENDING_SHIP",
                "statusText": "待发货",
                "latestTrace": None,
                "latestTraceAt": None,
                "eta": None,
            }
        elif status == "SHIPPING":
            shipped = f"2026-10-{min(day + 1, 28):02d}T09:00:00+08:00"
            logistics = {
                "packageCount": 1,
                "expressCompany": express_name,
                "trackingNo": f"{express_code}{8800000000 + seq}",
                "status": "IN_TRANSIT",
                "statusText": "运输中",
                "latestTrace": f"快件已到达【{city}转运中心】",
                "latestTraceAt": f"2026-10-{min(day + 2, 28):02d}T18:00:00+08:00",
                "eta": {
                    "predictArriveAt": f"2026-10-{min(day + 3, 28):02d}T18:00:00+08:00",
                    "predictArriveWindow": {
                        "earliest": f"2026-10-{min(day + 3, 28):02d}T14:00:00+08:00",
                        "latest": f"2026-10-{min(day + 3, 28):02d}T20:00:00+08:00",
                    },
                    "confidence": 0.8,
                    "delayRisk": "LOW",
                    "isOverdue": False,
                },
            }
        elif status == "DELIVERED":
            shipped = f"2026-10-{min(day + 1, 28):02d}T09:00:00+08:00"
            logistics = {
                "packageCount": 1,
                "expressCompany": express_name,
                "trackingNo": f"{express_code}{8800000000 + seq}",
                "status": "DELIVERED",
                "statusText": "已送达",
                "latestTrace": "快件已送达，待确认收货",
                "latestTraceAt": f"2026-10-{min(day + 3, 28):02d}T16:00:00+08:00",
                "eta": None,
            }
        elif status == "COMPLETED":
            shipped = f"2026-10-{min(day + 1, 28):02d}T09:00:00+08:00"
            completed = f"2026-10-{min(day + 4, 28):02d}T15:00:00+08:00"
            logistics = {
                "packageCount": 1,
                "expressCompany": express_name,
                "trackingNo": f"{express_code}{8800000000 + seq}",
                "status": "SIGNED",
                "statusText": "已签收",
                "latestTrace": "快件已签收",
                "latestTraceAt": f"2026-10-{min(day + 3, 28):02d}T15:30:00+08:00",
                "eta": None,
            }
            if i % 5 == 3:
                invoice = {
                    "eligible": True,
                    "invoiced": True,
                    "invoiceId": f"INV202610{day:02d}{seq:03d}",
                    "status": "ISSUED",
                }
        else:  # CANCELLED — 未付款取消，实付口径统一为 0
            cancelled = f"2026-10-{day:02d}T12:00:00+08:00"
            logistics = {
                "packageCount": 0,
                "expressCompany": None,
                "trackingNo": None,
                "status": "CANCELLED",
                "statusText": "已取消",
                "latestTrace": None,
                "latestTraceAt": None,
                "eta": None,
            }
            invoice = {"eligible": False, "invoiced": False, "invoiceId": None, "status": None}

        pay_channel = "WECHAT" if i % 2 == 0 else "ALIPAY"
        rows.append(
            {
                "orderId": order_id,
                "orderNo": order_no,
                "status": status,
                "statusText": status_text,
                "createdAt": created,
                "paidAt": paid,
                "shippedAt": shipped,
                "completedAt": completed,
                "cancelledAt": cancelled,
                "buyer": {"userId": "U10086", "nicknameMask": "王*"},
                "amounts": {
                    "goodsAmount": goods,
                    "freightAmount": freight,
                    "discountAmount": discount,
                    "payAmount": pay if paid else 0,
                    "currency": "CNY",
                },
                "payment": {
                    "payChannel": pay_channel if paid else None,
                    "payChannelText": ("微信支付" if pay_channel == "WECHAT" else "支付宝") if paid else None,
                    "transactionNo": f"{pay_channel.lower()}{202610000000 + seq}" if paid else None,
                    "paidAt": paid,
                },
                "items": [
                    {
                        "orderItemId": f"OI-E{seq}",
                        "skuId": product["skuId"],
                        "spuId": product["spuId"],
                        "spuName": product["spuName"],
                        "skuAttrs": product["skuAttrs"],
                        "quantity": qty,
                        "unitPrice": unit,
                        "payPrice": unit * qty - discount,
                        "imageUrl": f"https://cdn.example.com/sku/{product['skuId'].split('-')[-1]}.jpg",
                        "afterSaleStatus": None,
                    }
                ],
                "receiver": {
                    "nameMask": "张*",
                    "mobileMask": "138****0000",
                    "province": province,
                    "city": city,
                    "district": district,
                    "addressMask": address,
                },
                "merchant": {"merchantId": "M10001", "merchantName": "运动旗舰店"},
                "logisticsSummary": logistics,
                "afterSaleSummary": after_sale,
                "invoiceSummary": invoice,
                "remark": {
                    "buyerRemark": "请尽快发货" if status == "PAID" else None,
                    "merchantRemark": None,
                },
            }
        )
    return rows


EXTRA_ORDERS = _build_extra_orders(4)
# 运输中：挂退货售后，运单与 LOGISTICS 对齐
_shipping = EXTRA_ORDERS[1]
_shipping["afterSaleSummary"] = {
    "hasAfterSale": True,
    "activeCount": 1,
    "latestAfterSaleId": "AS20260925001",
}
_shipping["logisticsSummary"]["expressCompany"] = "顺丰速运"
_shipping["logisticsSummary"]["trackingNo"] = "SF1234567890"
_shipping["logisticsSummary"]["latestTrace"] = "快件已到达【上海转运中心】"
# 交易完成：挂已开具发票
_completed = EXTRA_ORDERS[3]
_completed["invoiceSummary"] = {
    "eligible": True,
    "invoiced": True,
    "invoiceId": "INV20260929001",
    "status": "ISSUED",
}

LOGISTICS = {
    "orderId": "O20261002002",
    "orderNo": "2026100210000002",
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
    "orderId": "O20261002002",
    "orderNo": "2026100210000002",
    "type": "RETURN",
    "typeText": "退货退款",
    "status": "RETURNING",
    "statusText": "退货寄回中",
    "reasonCode": "QUALITY",
    "reasonText": "商品质量问题",
    "applyAmount": 19800,
    "refundAmount": None,
    "currency": "CNY",
    "createdAt": "2026-09-25T11:00:00+08:00",
    "updatedAt": "2026-09-26T09:30:00+08:00",
    "items": [
        {
            "orderItemId": "OI-E2",
            "skuId": "SKU-7102",
            "spuName": "速干T恤",
            "quantity": 2,
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

# 完成态「仅退款」售后：挂在已完成订单 ORDER_2，与 REFUND 同售后单号，避免与运输中订单的退货单冲突
AFTER_SALE_COMPLETED = {
    "afterSaleId": "AS20260918008",
    "orderId": "O20260915008",
    "orderNo": "2026091508765432",
    "type": "REFUND_ONLY",
    "typeText": "仅退款",
    "status": "COMPLETED",
    "statusText": "已完成",
    "reasonCode": "NOT_WANT",
    "reasonText": "不想要了",
    "applyAmount": 45900,
    "refundAmount": 45900,
    "currency": "CNY",
    "createdAt": "2026-09-18T18:00:00+08:00",
    "updatedAt": "2026-09-18T18:20:00+08:00",
    "items": [
        {
            "orderItemId": "OI-2",
            "skuId": "SKU-6601",
            "spuName": "篮球鞋",
            "quantity": 1,
        }
    ],
    "progress": {
        "currentStep": "COMPLETED",
        "percent": 100,
        "steps": [
            {
                "step": "APPLIED",
                "stepText": "提交申请",
                "status": "DONE",
                "time": "2026-09-18T18:00:00+08:00",
                "desc": "已提交仅退款申请",
            },
            {
                "step": "MERCHANT_APPROVED",
                "stepText": "商家审核",
                "status": "DONE",
                "time": "2026-09-18T18:05:00+08:00",
                "desc": "商家已同意退款",
            },
            {
                "step": "REFUND_PROCESSING",
                "stepText": "退款处理",
                "status": "DONE",
                "time": "2026-09-18T18:06:00+08:00",
                "desc": "已发起支付渠道退款",
            },
            {
                "step": "COMPLETED",
                "stepText": "完成",
                "status": "DONE",
                "time": "2026-09-18T18:20:00+08:00",
                "desc": "退款已到账",
            },
        ],
    },
    "returnLogistics": None,
    "refund": {
        "refundId": "RF20260929001",
        "refundAmount": 45900,
        "refundStatus": "SUCCESS",
        "refundChannel": "WECHAT",
        "refundArriveAt": "2026-09-18T18:20:00+08:00",
        "refundArriveExpectAt": "2026-09-19T18:00:00+08:00",
    },
    "sla": {
        "nextActionOwner": None,
        "nextActionText": "售后已完成",
        "expectFinishAt": "2026-09-18T18:20:00+08:00",
    },
    "timeline": [
        {
            "time": "2026-09-18T18:20:00+08:00",
            "event": "COMPLETED",
            "title": "退款完成",
            "detail": "退款单 RF20260929001",
        }
    ],
    "rejectInfo": None,
}

REFUND = {
    "refundId": "RF20260929001",
    "afterSaleId": "AS20260918008",
    "orderId": "O20260915008",
    "orderNo": "2026091508765432",
    "type": "REFUND_ONLY",
    "typeText": "仅退款",
    "status": "SUCCESS",
    "statusText": "退款成功",
    "refundAmount": 45900,
    "currency": "CNY",
    "payChannel": "ALIPAY",
    "payChannelText": "原路退回支付宝",
    "transactionNo": "20260918xxxxxxx",
    "reasonCode": "NOT_WANT",
    "reasonText": "不想要了",
    "remark": "签收后申请仅退款（与商家协商免退货）",
    "items": [
        {
            "orderItemId": "OI-2",
            "skuId": "SKU-6601",
            "spuName": "篮球鞋",
            "quantity": 1,
            "refundAmount": 45900,
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
                "time": "2026-09-18T18:00:00+08:00",
                "desc": "已提交仅退款申请",
            },
            {
                "step": "MERCHANT_APPROVED",
                "stepText": "商家审核",
                "status": "DONE",
                "time": "2026-09-18T18:05:00+08:00",
                "desc": "商家已同意退款",
            },
            {
                "step": "REFUNDING",
                "stepText": "退款执行中",
                "status": "DONE",
                "time": "2026-09-18T18:06:00+08:00",
                "desc": "已发起支付渠道退款",
            },
            {
                "step": "ARRIVED",
                "stepText": "到账完成",
                "status": "DONE",
                "time": "2026-09-18T18:20:00+08:00",
                "desc": "退款已原路退回支付宝",
            },
        ],
    },
    "appliedAt": "2026-09-18T18:00:00+08:00",
    "approvedAt": "2026-09-18T18:05:00+08:00",
    "refundingAt": "2026-09-18T18:06:00+08:00",
    "expectArriveAt": "2026-09-19T18:00:00+08:00",
    "arrivedAt": "2026-09-18T18:20:00+08:00",
    "failReason": None,
    "updatedAt": "2026-09-18T18:20:00+08:00",
}

INVOICE = {
    "invoiceId": "INV20260929001",
    "applicationNo": "IA20260929001",
    "orderId": "O20261004004",
    "orderNo": "2026100410000004",
    "status": "ISSUED",
    "statusText": "已开票",
    "invoiceType": "ELECTRONIC_NORMAL",
    "invoiceTypeText": "电子普通发票",
    "amount": 15300,
    "currency": "CNY",
    "title": {
        "titleType": "ENTERPRISE",
        "titleName": "某某科技有限公司",
        "taxNo": "91310000MA1XXXXXX",
    },
    "invoiceCode": "04400xxxxxx",
    "invoiceNumber": "12345678",
    "checkCode": "12345678901234567890",
    "issuedAt": "2026-09-29T10:18:00+08:00",
    "buyer": {"name": "某某科技有限公司", "taxNo": "91310000MA1XXXXXX"},
    "seller": {"name": "运动旗舰店所属主体", "taxNo": "91310000MA2XXXXXX"},
    "lineItems": [
        {
            "name": "健身护腕",
            "spec": "黑色 / 一对",
            "unit": "件",
            "quantity": "2",
            "unitPrice": 7900,
            "amount": 15300,
            "taxRate": "0.13",
            "taxAmount": 1761,
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
        ],
    },
    "failReason": None,
}


def _clone(obj: Any) -> Any:
    return deepcopy(obj)


def all_orders() -> list[dict[str, Any]]:
    return [_clone(ORDER_2)] + [_clone(o) for o in EXTRA_ORDERS]


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
    return [_clone(AFTER_SALE), _clone(AFTER_SALE_COMPLETED)]


def get_after_sale(after_sale_id: str) -> dict[str, Any] | None:
    for item in all_after_sales():
        if item["afterSaleId"] == after_sale_id:
            return item
    return None


def all_refunds() -> list[dict[str, Any]]:
    return [_clone(REFUND)] + _load_created_refunds()


def _load_created_refunds() -> list[dict[str, Any]]:
    from app.core.database.redis_client import get_redis

    client = get_redis(for_stream=True)
    if client is not None:
        raw = client.get("oa:fake:created_refunds")
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    return [_clone(item) for item in data if isinstance(item, dict)]
            except Exception:
                pass
        return []
    return [_clone(item) for item in _CREATED_REFUNDS]


def _persist_created_refund(created: dict[str, Any]) -> None:
    from app.core.database.redis_client import get_redis

    client = get_redis(for_stream=True)
    if client is None:
        _CREATED_REFUNDS.append(created)
        return
    rows = _load_created_refunds()
    rows.append(created)
    client.setex("oa:fake:created_refunds", 2 * 60 * 60, json.dumps(rows, ensure_ascii=False))


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
    _persist_created_refund(created)
    return _clone(created)


def all_invoices() -> list[dict[str, Any]]:
    return [_clone(INVOICE)]


def get_invoice(invoice_id: str) -> dict[str, Any] | None:
    for item in all_invoices():
        if item["invoiceId"] == invoice_id:
            return item
    return None
