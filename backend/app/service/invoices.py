from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote

from app.service import fake_data


def get_invoice(
    invoice_id: str,
    *,
    include_files: bool = True,
    include_progress: bool = True,
) -> dict[str, Any]:
    item = fake_data.get_invoice(invoice_id)
    if not item:
        return {"error": {"code": 50004, "message": "发票不存在或无权访问"}}
    data = dict(item)
    if not include_files:
        data.pop("files", None)
    if not include_progress:
        data.pop("progress", None)
    return data


def list_by_order(
    *,
    order_id: Optional[str] = None,
    order_no: Optional[str] = None,
    status: Optional[str] = None,
    invoice_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    if not order_id and not order_no:
        return {"error": {"code": 400, "message": "orderId 与 orderNo 二选一必填"}}

    statuses = {s.strip() for s in status.split(",")} if status else set()
    rows = fake_data.all_invoices()
    filtered = []
    for item in rows:
        if order_id and item["orderId"] != order_id:
            continue
        if order_no and item["orderNo"] != order_no:
            continue
        if statuses and item["status"] not in statuses:
            continue
        if invoice_type and item["invoiceType"] != invoice_type:
            continue
        filtered.append(
            {
                "invoiceId": item["invoiceId"],
                "applicationNo": item["applicationNo"],
                "status": item["status"],
                "statusText": item["statusText"],
                "invoiceType": item["invoiceType"],
                "invoiceTypeText": item["invoiceTypeText"],
                "amount": item["amount"],
                "currency": item["currency"],
                "titleName": item["title"]["titleName"],
                "invoiceCode": item["invoiceCode"],
                "invoiceNumber": item["invoiceNumber"],
                "issuedAt": item["issuedAt"],
                "hasDownloadableFile": bool(item.get("files")),
                "fileTypes": [f["type"] for f in item.get("files") or []],
            }
        )

    if not filtered:
        # still success with empty list per api.md
        oid = order_id
        ono = order_no
        if not oid or not ono:
            order = (
                fake_data.get_order_by_id(order_id)
                if order_id
                else fake_data.get_order_by_no(order_no or "")
            )
            if order:
                oid = order["orderId"]
                ono = order["orderNo"]
        return {
            "orderId": oid,
            "orderNo": ono,
            "list": [],
            "page": page,
            "pageSize": page_size,
            "total": 0,
            "hasMore": False,
        }

    first = next(
        i
        for i in fake_data.all_invoices()
        if (order_id and i["orderId"] == order_id) or (order_no and i["orderNo"] == order_no)
    )
    total = len(filtered)
    start = max(page - 1, 0) * page_size
    end = start + page_size
    return {
        "orderId": first["orderId"],
        "orderNo": first["orderNo"],
        "list": filtered[start:end],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "hasMore": end < total,
    }


def create_download_urls(
    invoice_id: str,
    *,
    types: Optional[list[str]] = None,
    expire_seconds: int = 1800,
) -> dict[str, Any]:
    item = fake_data.get_invoice(invoice_id)
    if not item:
        return {"error": {"code": 50004, "message": "发票不存在或无权访问"}}
    if item["status"] not in {"ISSUED", "PUSHED"}:
        return {"error": {"code": 50005, "message": "发票尚未开具，无法下载"}}

    wanted = [str(t).strip().upper() for t in (types or ["PDF"]) if str(t).strip()]
    if not wanted:
        wanted = ["PDF"]
    supported = {"PDF", "OFD", "XML"}
    if any(t not in supported for t in wanted):
        return {"error": {"code": 50009, "message": "请求的文件类型不支持"}}

    expire_seconds = max(900, min(expire_seconds, 3600))
    expire_at = datetime.now(timezone(timedelta(hours=8))) + timedelta(seconds=expire_seconds)
    expire_iso = expire_at.isoformat()

    files = []
    existing = {f["type"]: f for f in item.get("files") or []}
    for t in wanted:
        base = existing.get(t, {})
        size = base.get("sizeBytes", 102400)
        file_name = f"{invoice_id}.{t.lower()}"
        url = (
            f"https://cdn.example.com/inv/{quote(file_name)}"
            f"?sign=fake&e={int(expire_at.timestamp())}"
        )
        files.append(
            {
                "type": t,
                "url": url,
                "expireAt": expire_iso,
                "sizeBytes": size,
                "fileName": file_name,
            }
        )

    return {"invoiceId": invoice_id, "status": item["status"], "files": files}
