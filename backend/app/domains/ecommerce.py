"""电商客服域：订单 / 物流 / 发票 / 售后 / 退款 的平台钩子。

由各 Agent 进程在入口调用 register_ecommerce_domain() 安装。
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.agent import domain_registry as registry
from app.core.agent.tools.registry import slim_invoice_for_agent
from app.service import after_sales as after_sale_service
from app.service import invoices as invoice_service
from app.service import logistics as logistics_service
from app.service import orders as order_service
from app.service import refunds as refund_service

_PACK_ID = "ecommerce"

_LIST_TOOLS = frozenset(
    {
        "query_orders",
        "list_after_sales",
        "list_refunds",
        "list_invoices_by_order",
    }
)

_BUSINESS_TOOLS = frozenset(
    {
        "query_orders",
        "get_order_detail",
        "get_order_by_no",
        "get_logistics_by_order_no",
        "get_logistics_tracking",
        "list_after_sales",
        "get_after_sale_detail",
        "get_after_sale_progress",
        "list_refunds",
        "get_refund_detail",
        "get_refund_progress",
        "create_refund",
        "get_invoice",
        "list_invoices_by_order",
        "create_invoice_download_urls",
        "dispatch_order_expert",
        "dispatch_logistics_expert",
        "dispatch_invoice_expert",
        "submit_expert_report",
    }
)

_DOMAIN_MARKERS = (
    "订单",
    "退款",
    "退货",
    "物流",
    "运单",
    "发票",
    "售后",
    "快递",
)

_LIST_EVIDENCE_SOURCES = frozenset(
    {
        "query_orders",
        "order_list",
        "list",
    }
)


def _step_observation(step: dict[str, Any]) -> Any:
    obs = step.get("observation")
    if isinstance(obs, str):
        try:
            return json.loads(obs)
        except Exception:
            return obs
    return obs


def conclusion_from_query_orders_steps(steps: list[dict[str, Any]] | None) -> str | None:
    """若已成功调用 query_orders，从列表结果生成可对用户展示的结论（兜底）。"""
    for step in reversed(steps or []):
        if str(step.get("tool") or "") != "query_orders":
            continue
        obs = _step_observation(step)
        if not isinstance(obs, dict) or obs.get("error"):
            continue
        rows = obs.get("list")
        if not isinstance(rows, list):
            continue
        total = int(obs.get("total") if obs.get("total") is not None else len(rows))
        if total == 0 and not rows:
            return "未查询到订单。"
        lines: list[str] = [f"共查到 {total} 笔订单（本页 {len(rows)} 笔）："]
        for idx, row in enumerate(rows[:20], 1):
            if not isinstance(row, dict):
                continue
            pay = row.get("payAmount")
            if isinstance(pay, (int, float)):
                amount = f"{pay / 100:.2f} 元"
            else:
                amount = "—"
            names = row.get("itemNames") or []
            if isinstance(names, list) and names:
                goods = "、".join(str(n) for n in names[:3] if n)
            else:
                goods = "—"
            lines.append(
                f"{idx}. 订单号 {row.get('orderNo') or '—'}｜"
                f"{row.get('statusText') or row.get('status') or '—'}｜"
                f"实付 {amount}｜{goods}"
            )
        if total > len(rows):
            lines.append("（还有更多，可说明要看第几页或按状态筛选。）")
        return "\n".join(lines)
    return None


def _is_order_list_text(text: str) -> bool:
    body = (text or "").strip()
    if body == "未查询到订单。":
        return True
    first = body.splitlines()[0] if body else ""
    return first.startswith("共查到 ") and "订单号" in body


def _reply_keeps_order_lines(raw: str, listing: str) -> bool:
    numbers = re.findall(r"订单号\s+([^\s｜|，,]+)", listing)
    if not numbers:
        return listing.strip() in (raw or "")
    return all(num.rstrip("｜|") in (raw or "") for num in numbers)


def prefer_order_list_reply(raw: str, conclusions: list[str] | None) -> str:
    """订单列表已被派发结论写好时，不用路由模型的汇总替换逐笔列表。"""
    text = (raw or "").strip()
    lists = [c.strip() for c in (conclusions or []) if isinstance(c, str) and _is_order_list_text(c)]
    if not lists:
        return text
    listing = lists[-1]
    if _reply_keeps_order_lines(text, listing):
        return text
    others = [
        c.strip()
        for c in (conclusions or [])
        if isinstance(c, str) and c.strip() and c.strip() not in lists
    ]
    if others:
        return listing + "\n\n" + "\n\n".join(others)
    return listing


def _ok_payload(data: Any) -> Any | None:
    if not isinstance(data, dict) or data.get("error"):
        return None
    return data


def _fetch_order_id(rid: str) -> Any | None:
    return _ok_payload(order_service.get_order_detail(order_id=rid))


def _fetch_order_no(rid: str) -> Any | None:
    return _ok_payload(order_service.get_order_detail(order_no=rid))


def _fetch_invoice(rid: str) -> Any | None:
    return _ok_payload(invoice_service.get_invoice(rid))


def _fetch_refund(rid: str) -> Any | None:
    return _ok_payload(refund_service.get_refund_detail(rid))


def _fetch_after_sale(rid: str) -> Any | None:
    return _ok_payload(after_sale_service.get_after_sale_detail(rid))


def _fetch_logistics(rid: str) -> Any | None:
    return _ok_payload(logistics_service.get_by_order_no(rid))


def register_ecommerce_domain() -> None:
    """幂等安装电商域钩子。"""
    if not registry.mark_pack_registered(_PACK_ID):
        return

    registry.register_evidence_fetcher("order", _fetch_order_id)
    registry.register_evidence_fetcher("order_id", _fetch_order_id)
    registry.register_evidence_fetcher("order_no", _fetch_order_no)
    registry.register_evidence_fetcher("invoice", _fetch_invoice)
    registry.register_evidence_fetcher("invoice_id", _fetch_invoice)
    registry.register_evidence_fetcher("refund", _fetch_refund)
    registry.register_evidence_fetcher("refund_id", _fetch_refund)
    registry.register_evidence_fetcher("after_sale", _fetch_after_sale)
    registry.register_evidence_fetcher("after_sale_id", _fetch_after_sale)
    registry.register_evidence_fetcher("logistics", _fetch_logistics)
    registry.register_evidence_fetcher("tracking_no", _fetch_logistics)
    registry.register_evidence_fetcher("order_no_logistics", _fetch_logistics)

    registry.register_list_tools(_LIST_TOOLS)
    registry.register_list_evidence_sources(_LIST_EVIDENCE_SOURCES)
    registry.register_business_tools(_BUSINESS_TOOLS)
    registry.register_domain_markers(_DOMAIN_MARKERS)
    registry.register_list_conclusion_formatter(conclusion_from_query_orders_steps)
    registry.register_prefer_reply_hook(prefer_order_list_reply)
    registry.register_result_view("get_invoice", slim_invoice_for_agent)
    registry.register_supplement_hint("不要引用其他专家的结论作为证据")
    registry.register_supplement_hint("不要向用户索要手机号/账号")
    registry.register_supplement_hint("「查看全部订单」应直接 query_orders")
    registry.set_human_cs_scope_blurb("订单、物流、售后、退款和发票相关问题")


def ensure_ecommerce_domain() -> None:
    """供单测 / 延迟路径：确保电商域已安装。"""
    register_ecommerce_domain()
