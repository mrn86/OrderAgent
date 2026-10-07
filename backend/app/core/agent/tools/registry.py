"""发票详情送模视图。业务工具由各 Agent 进程自行创建，不在此注册。"""

from __future__ import annotations

import re
from typing import Any

_EMAIL_KEY = re.compile(r"^(e[_-]?mail|mail)$", re.I)
_PUSHED_EMAIL_STEP = re.compile(r"发送邮箱|发邮件|邮件推送")


def _drop_email_keys(value: Any) -> Any:
    """递归删除 email/mail 键，避免送模。"""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _EMAIL_KEY.match(str(key)):
                continue
            out[str(key)] = _drop_email_keys(item)
        return out
    if isinstance(value, list):
        return [_drop_email_keys(item) for item in value]
    return value


def _party_for_agent(party: Any) -> dict[str, Any] | None:
    if not isinstance(party, dict):
        return None
    return {
        "name": party.get("name"),
        "taxNo": party.get("taxNo"),
    }


def slim_invoice_for_agent(payload: dict[str, Any]) -> dict[str, Any]:
    """发票详情送模视图：allowlist + 去掉邮件与「已发送邮箱」进度。"""
    if not isinstance(payload, dict):
        return payload
    if payload.get("error"):
        return _drop_email_keys(payload)

    title_in = payload.get("title") if isinstance(payload.get("title"), dict) else {}
    title = {
        "titleType": title_in.get("titleType"),
        "titleName": title_in.get("titleName"),
        "taxNo": title_in.get("taxNo"),
    }

    progress_in = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    steps_out: list[dict[str, Any]] = []
    for step in progress_in.get("steps") or []:
        if not isinstance(step, dict):
            continue
        code = str(step.get("step") or "").upper()
        text = str(step.get("stepText") or "")
        if code == "PUSHED" or _PUSHED_EMAIL_STEP.search(text):
            continue
        steps_out.append(
            {
                "step": step.get("step"),
                "stepText": step.get("stepText"),
                "status": step.get("status"),
                "time": step.get("time"),
            }
        )
    current = str(progress_in.get("currentStep") or "")
    if current.upper() == "PUSHED" or _PUSHED_EMAIL_STEP.search(current):
        current = str(steps_out[-1].get("step") or "ISSUED") if steps_out else ""

    slim: dict[str, Any] = {
        "invoiceId": payload.get("invoiceId"),
        "applicationNo": payload.get("applicationNo"),
        "orderId": payload.get("orderId"),
        "orderNo": payload.get("orderNo"),
        "status": payload.get("status"),
        "statusText": payload.get("statusText"),
        "invoiceType": payload.get("invoiceType"),
        "invoiceTypeText": payload.get("invoiceTypeText"),
        "amount": payload.get("amount"),
        "currency": payload.get("currency"),
        "title": title,
        "invoiceCode": payload.get("invoiceCode"),
        "invoiceNumber": payload.get("invoiceNumber"),
        "checkCode": payload.get("checkCode"),
        "issuedAt": payload.get("issuedAt"),
        "buyer": _party_for_agent(payload.get("buyer")),
        "seller": _party_for_agent(payload.get("seller")),
        "lineItems": payload.get("lineItems") or [],
        "files": payload.get("files") or [],
        "progress": {
            "currentStep": current,
            "steps": steps_out,
        },
        "failReason": payload.get("failReason"),
    }
    return _drop_email_keys(slim)
