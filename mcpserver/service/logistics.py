from __future__ import annotations

from typing import Any, Optional

from data import fake_data


def get_by_order_no(order_no: str, *, include_eta: bool = True) -> dict[str, Any]:
    data = fake_data.get_logistics_by_order_no(order_no)
    if not data:
        return {"error": {"code": 30001, "message": "订单不存在或无权访问"}}
    if not data.get("packages"):
        return {"error": {"code": 30002, "message": "订单尚未发货，无物流"}}
    if not include_eta:
        for pkg in data["packages"]:
            pkg["eta"] = None
    return data


def get_by_tracking(
    tracking_no: str,
    *,
    express_company_code: Optional[str] = None,
    include_eta: bool = True,
) -> dict[str, Any]:
    data = fake_data.get_tracking(tracking_no, express_company_code)
    if not data:
        return {"error": {"code": 30003, "message": "运单号无效 / 快递公司不匹配"}}
    if not include_eta:
        data["eta"] = None
    return data
