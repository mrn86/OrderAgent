"""路由 ↔ 专家 Redis 总线信封与 ExpertReport。专家之间无通道。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field

ExpertName = Literal["order", "logistics", "invoice"]
TaskMode = Literal["execute", "supplement", "review"]
ReportStatus = Literal["done", "failed", "need_hitl", "need_more_info"]
EventType = Literal["progress", "approval_required", "report", "failed"]


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class EvidenceItem(BaseModel):
    source: str
    id: str = ""
    excerpt: str = ""
    fetched_at: str = ""
    result_hash: str = ""


class PathStep(BaseModel):
    step: str
    detail: str = ""


class CommandRecord(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    result_hash: str = ""
    ok: bool = True


class ExpertReport(BaseModel):
    conclusion: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    path: list[PathStep] = Field(default_factory=list)
    commands: list[CommandRecord] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    unresolved: list[str] = Field(default_factory=list)
    suggested_next: list[str] = Field(default_factory=list)
    status: ReportStatus = "done"
    task_id: str = ""
    expert: str = ""

    def output_summary(self, limit: int = 400) -> str:
        text = (self.conclusion or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit] + "…"


class DispatchEnvelope(BaseModel):
    task_id: str
    trace_id: str
    conversation_id: str
    user_id: str = "anonymous"
    expert: ExpertName
    mode: TaskMode = "execute"
    reason: str
    input_summary: str
    instruction: str
    constraints: str = ""
    timeout_ms: int = 120000
    parent_task_id: str | None = None

    def brief(self) -> str:
        return f"[{self.expert}/{self.mode}] {self.reason}: {self.input_summary}"


class TaskEvent(BaseModel):
    type: EventType
    task_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ControlMessage(BaseModel):
    action: Literal["approve", "reject", "cancel"]
    task_id: str
    conversation_id: str = ""


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


def report_from_answer(
    answer: str,
    *,
    task_id: str,
    expert: str,
    steps: list[dict[str, Any]] | None = None,
) -> ExpertReport:
    """优先解析 JSON；否则把自由文本降级包装为低置信度报告。"""
    text = (answer or "").strip()
    cmds = commands_from_steps(steps or [])
    list_conclusion = conclusion_from_query_orders_steps(steps)
    parsed = _extract_json_object(text)
    if parsed:
        try:
            if "conclusion" not in parsed:
                parsed["conclusion"] = text[:500] or "（无结论）"
            report = ExpertReport.model_validate(parsed)
            report.task_id = report.task_id or task_id
            report.expert = report.expert or expert
            if not report.commands and cmds:
                report.commands = cmds
            # 列表查询已成功但结论空/敷衍时，用列表生成结论
            weak = not (report.conclusion or "").strip() or report.status == "need_more_info"
            if list_conclusion and weak:
                report.conclusion = list_conclusion
                report.status = "done"
                if report.confidence < 0.75:
                    report.confidence = 0.85
                report.unresolved = [u for u in report.unresolved if "未能解析" not in u]
            return report
        except Exception:
            pass
    if list_conclusion:
        return ExpertReport(
            conclusion=list_conclusion,
            commands=cmds,
            confidence=0.85,
            status="done",
            task_id=task_id,
            expert=expert,
        )
    return ExpertReport(
        conclusion=text or "专家未返回结构化结论",
        commands=cmds,
        confidence=0.35,
        unresolved=["未能解析 ExpertReport JSON"],
        suggested_next=["要求专家以 submit_expert_report 回传"],
        status="need_more_info",
        task_id=task_id,
        expert=expert,
    )


_WEAK_LIST_CONCLUSION = (
    "手机号",
    "账号",
    "未能返回有效",
    "需要补充",
    "提供以下",
    "订单号（如有",
    "大致时间",
)


def upgrade_report_with_list_steps(
    report: ExpertReport,
    steps: list[dict[str, Any]] | None,
) -> ExpertReport:
    """列表工具已成功时，避免错误的 need_more_info / 向用户追问覆盖真实列表结论。"""
    list_conclusion = conclusion_from_query_orders_steps(steps)
    if not list_conclusion:
        return report
    if not report.commands:
        report.commands = commands_from_steps(steps or [])
    text = report.conclusion or ""
    weak = (
        report.status in {"need_more_info", "failed"}
        or not text.strip()
        or any(m in text for m in _WEAK_LIST_CONCLUSION)
    )
    if weak:
        report.conclusion = list_conclusion
        report.status = "done"
        report.confidence = max(float(report.confidence or 0), 0.85)
        report.unresolved = [
            u
            for u in (report.unresolved or [])
            if "未能解析" not in u and "补充" not in u
        ]
    return report


def commands_from_steps(steps: list[dict[str, Any]]) -> list[CommandRecord]:
    out: list[CommandRecord] = []
    for step in steps or []:
        name = str(step.get("tool") or "")
        if not name or name == "submit_expert_report":
            continue
        obs = step.get("observation")
        out.append(
            CommandRecord(
                tool=name,
                args=step.get("input") if isinstance(step.get("input"), dict) else {},
                result_hash=canonical_hash(obs) if obs is not None else "",
                ok="error" not in (obs if isinstance(obs, dict) else {}),
            )
        )
    return out


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
        return data if isinstance(data, dict) else None
    except Exception:
        return None
