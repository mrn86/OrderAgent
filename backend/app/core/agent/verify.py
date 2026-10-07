"""路由对专家报告的证据复核：不盲信结论，重查关键 ID 并比对 hash。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.service import fake_data
from app.core.agent.protocol import ExpertReport, canonical_hash
from app.service import invoices as invoice_service
from app.service import refunds as refund_service


@dataclass
class VerifyResult:
    ok: bool
    issues: list[str] = field(default_factory=list)
    need_supplement: bool = False
    need_review: bool = False


def _live_record(source: str, record_id: str) -> Any | None:
    src = (source or "").strip().lower()
    rid = (record_id or "").strip()
    if not rid:
        return None
    if src in {"order", "order_id"}:
        return fake_data.get_order_by_id(rid)
    if src in {"order_no"}:
        return fake_data.get_order_by_no(rid)
    if src in {"invoice", "invoice_id"}:
        return fake_data.get_invoice(rid) or invoice_service.get_invoice(rid)
    if src in {"refund", "refund_id"}:
        return fake_data.get_refund(rid) or refund_service.get_refund_detail(rid)
    if src in {"after_sale", "after_sale_id"}:
        return fake_data.get_after_sale(rid)
    if src in {"logistics", "tracking_no", "order_no_logistics"}:
        return fake_data.get_logistics_by_order_no(rid)
    return None


_LIST_TOOLS = frozenset(
    {
        "query_orders",
        "list_after_sales",
        "list_refunds",
        "list_invoices_by_order",
    }
)


def _has_successful_list_command(report: ExpertReport) -> bool:
    for cmd in report.commands or []:
        if cmd.tool in _LIST_TOOLS and cmd.ok:
            return True
    return False


def verify_report(report: ExpertReport, *, min_confidence: float = 0.55) -> VerifyResult:
    issues: list[str] = []
    list_ok = _has_successful_list_command(report)
    if not (report.conclusion or "").strip():
        issues.append("缺少结论")
    if report.confidence < min_confidence and not list_ok:
        issues.append(f"置信度偏低（{report.confidence:.2f}）")
    if not report.evidence and not report.commands:
        issues.append("缺少证据与工具路径")

    for item in report.evidence:
        src = (item.source or "").strip().lower()
        # 列表类证据：有成功 list 工具路径即可，不做单 ID hash 强校验
        if src in {"query_orders", "order_list", "list"} or item.id in {"*", "list", "page"}:
            if not list_ok and not _live_record("order_id", item.id):
                # 无 list 命令时仍尝试按 order_id 复核
                if src in {"order", "order_id"}:
                    pass
                else:
                    continue
            if list_ok:
                continue
        live = _live_record(item.source, item.id)
        if live is None:
            issues.append(f"无法复核证据 {item.source}:{item.id}")
            continue
        if isinstance(live, dict) and live.get("error"):
            issues.append(f"证据 {item.source}:{item.id} 复核失败")
            continue
        if item.result_hash:
            digest = canonical_hash(live)
            if digest != item.result_hash:
                issues.append(f"证据 {item.source}:{item.id} 与权威数据不一致")

    conflict = any("不一致" in x or "无法复核" in x for x in issues)
    # 列表查询已成功且有结论：不因 need_more_info/低置信度再逼专家「向用户追问」
    soft_low = report.confidence < min_confidence or report.status in {"need_more_info", "failed"}
    if list_ok and (report.conclusion or "").strip() and report.status != "failed":
        soft_low = False
        issues = [i for i in issues if "置信度偏低" not in i]
    need_review = conflict
    need_supplement = (not conflict) and (soft_low or bool(issues))
    ok = not issues
    return VerifyResult(
        ok=ok,
        issues=issues,
        need_supplement=need_supplement and not need_review,
        need_review=need_review,
    )
