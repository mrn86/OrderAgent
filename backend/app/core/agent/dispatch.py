"""路由派发：A2A Client 调用专家，复核后必要时再派发。"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from app.core.agent.bus import (
    clear_pending_hitl,
    get_pending_hitl,
    load_meta,
    save_meta,
    set_pending_hitl,
)
from app.core.agent.protocol import DispatchEnvelope, ExpertReport, report_from_answer
from app.core.agent.verify import verify_report
from app.core.audit.task import emit_agent_task
from app.core.audit import get_audit_request_id, get_trace_id
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_send_impl: Callable[[DispatchEnvelope], dict[str, Any]] | None = None
_resume_impl: Callable[[str, str, str], dict[str, Any]] | None = None


def bind_a2a_client(
    *,
    send: Callable[[DispatchEnvelope], dict[str, Any]],
    resume: Callable[[str, str, str], dict[str, Any]],
) -> None:
    """由路由进程安装自己的 A2A Client。"""
    global _send_impl, _resume_impl
    _send_impl = send
    _resume_impl = resume


def send_dispatch(envelope: DispatchEnvelope) -> dict[str, Any]:
    if _send_impl is None:
        return {"type": "failed", "payload": {"message": "A2A 客户端未安装"}}
    return _send_impl(envelope)


def resume_via_http(expert: str, task_id: str, action: str) -> dict[str, Any]:
    if _resume_impl is None:
        return {"type": "failed", "payload": {"message": "A2A 客户端未安装"}}
    return _resume_impl(expert, task_id, action)


def _summarize(text: str, limit: int = 240) -> str:
    value = " ".join((text or "").split())
    if len(value) <= limit:
        return value
    return value[:limit] + "…"


def slim_dispatch_for_agent(result: dict[str, Any]) -> dict[str, Any]:
    """派发给路由模型 / 前端的业务摘要：不含 report 全量、progress、evidence。"""
    if not isinstance(result, dict):
        return {"ok": False, "status": "failed", "conclusion": str(result), "message": str(result)}

    report = result.get("report") if isinstance(result.get("report"), dict) else {}
    verified_in = result.get("verified") if isinstance(result.get("verified"), dict) else None
    follow = result.get("followUp") if isinstance(result.get("followUp"), dict) else None

    conclusion = (
        (follow or {}).get("conclusion")
        or report.get("conclusion")
        or result.get("conclusion")
        or result.get("message")
        or ""
    )
    status = (follow or {}).get("status") or result.get("status") or report.get("status") or "failed"
    risks = (follow or {}).get("risks")
    if risks is None:
        risks = report.get("risks") or result.get("risks") or []
    unresolved = (follow or {}).get("unresolved")
    if unresolved is None:
        unresolved = report.get("unresolved") or result.get("unresolved") or []

    verified = None
    src_verified = (follow or {}).get("verified") if follow and follow.get("verified") is not None else verified_in
    if isinstance(src_verified, dict):
        verified = {
            "ok": bool(src_verified.get("ok")),
            "issues": list(src_verified.get("issues") or []),
        }

    out: dict[str, Any] = {
        "ok": bool(result.get("ok", False)),
        "status": status,
        "taskId": result.get("taskId") or report.get("task_id") or "",
        "expert": result.get("expert") or report.get("expert") or "",
        "conclusion": str(conclusion or "").strip(),
        "risks": list(risks) if isinstance(risks, list) else [],
        "unresolved": list(unresolved) if isinstance(unresolved, list) else [],
    }
    tools: list[str] = []
    for cmd in report.get("commands") or []:
        tool_name = cmd.get("tool") if isinstance(cmd, dict) else None
        if isinstance(tool_name, str):
            tool_name = tool_name.strip()
            if tool_name and tool_name != "submit_expert_report":
                tools.append(tool_name)
    if tools:
        out["tools"] = tools
    if verified is not None:
        out["verified"] = verified
    if result.get("message"):
        out["message"] = str(result["message"])
    approval = result.get("approvalRequired")
    if isinstance(approval, dict):
        out["approvalRequired"] = {
            "requestId": approval.get("requestId") or approval.get("taskId"),
            "tool": approval.get("tool"),
            "summary": approval.get("summary") or "",
            "conversationId": approval.get("conversationId") or "",
            "taskId": approval.get("taskId"),
            "args": approval.get("args") if isinstance(approval.get("args"), dict) else {},
        }
    return out


def dispatch_expert(
    *,
    expert: str,
    instruction: str,
    reason: str,
    conversation_id: str,
    user_id: str = "anonymous",
    mode: str = "execute",
    constraints: str = "",
    parent_task_id: str | None = None,
    verify: bool = True,
    _retry_depth: int = 0,
) -> dict[str, Any]:
    settings = get_settings()
    timeout_ms = int(settings.expert_task_timeout_ms)
    envelope = DispatchEnvelope(
        task_id=str(uuid.uuid4()),
        trace_id=get_trace_id() or get_audit_request_id() or envelope_trace(),
        conversation_id=conversation_id,
        user_id=user_id,
        expert=expert,  # type: ignore[arg-type]
        mode=mode,  # type: ignore[arg-type]
        reason=reason.strip() or "router_dispatch",
        input_summary=_summarize(instruction),
        instruction=instruction,
        constraints=constraints,
        timeout_ms=timeout_ms,
        parent_task_id=parent_task_id,
    )
    started = time.perf_counter()
    save_meta(
        envelope.task_id,
        envelope.model_dump() | {"status": "dispatched", "transport": "a2a"},
    )
    emit_agent_task(
        phase="created",
        reason=envelope.reason,
        input_summary=envelope.input_summary,
        task_id=envelope.task_id,
        expert=expert,
        conversation_id=conversation_id,
        mode=mode,
    )

    outcome = send_dispatch(envelope)
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    etype = str(outcome.get("type") or "failed")
    payload = outcome.get("payload") if isinstance(outcome.get("payload"), dict) else {}

    if etype == "approval_required":
        set_pending_hitl(conversation_id, envelope.task_id)
        emit_agent_task(
            phase="approval_required",
            reason=envelope.reason,
            input_summary=envelope.input_summary,
            task_id=envelope.task_id,
            expert=expert,
            conversation_id=conversation_id,
            mode=mode,
            latency_ms=elapsed,
        )
        return slim_dispatch_for_agent(
            {
                "ok": True,
                "status": "need_hitl",
                "taskId": envelope.task_id,
                "expert": expert,
                "approvalRequired": payload,
                "message": "专家任务等待用户审批高风险操作，本轮结束，勿再调用工具。",
                "conclusion": "有待审批的专家操作，请先确认是否批准。",
            }
        )

    if etype != "report":
        fail_reason = str(payload.get("message") or "专家任务失败")
        emit_agent_task(
            phase="failed",
            reason=envelope.reason,
            input_summary=envelope.input_summary,
            output_summary=fail_reason,
            failure_reason=fail_reason,
            task_id=envelope.task_id,
            expert=expert,
            conversation_id=conversation_id,
            mode=mode,
            latency_ms=elapsed,
        )
        return slim_dispatch_for_agent(
            {
                "ok": False,
                "status": "failed",
                "taskId": envelope.task_id,
                "expert": expert,
                "message": fail_reason,
                "conclusion": fail_reason,
            }
        )

    try:
        report = ExpertReport.model_validate(payload)
    except Exception:
        report = report_from_answer(str(payload), task_id=envelope.task_id, expert=expert)

    report.task_id = report.task_id or envelope.task_id
    report.expert = report.expert or expert
    verified_payload: dict[str, Any] | None = None
    follow_slim: dict[str, Any] | None = None

    if verify:
        verdict = verify_report(report)
        verified_payload = {
            "ok": verdict.ok,
            "issues": verdict.issues,
            "needSupplement": verdict.need_supplement,
            "needReview": verdict.need_review,
        }
        if _retry_depth < 1 and (verdict.need_supplement or verdict.need_review):
            next_mode = "review" if verdict.need_review else "supplement"
            extra = (
                "路由复核发现问题，请用业务工具补证据并重新 submit_expert_report："
                + "；".join(verdict.issues)
                + "。不要引用其他专家的结论作为证据；"
                "不要向用户索要手机号/账号；「查看全部订单」应直接 query_orders。"
            )
            follow_slim = dispatch_expert(
                expert=expert,
                instruction=instruction + "\n\n" + extra,
                reason=f"verify_{next_mode}",
                conversation_id=conversation_id,
                user_id=user_id,
                mode=next_mode,
                constraints=constraints,
                parent_task_id=envelope.task_id,
                verify=True,
                _retry_depth=_retry_depth + 1,
            )

    emit_agent_task(
        phase="done",
        reason=envelope.reason,
        input_summary=envelope.input_summary,
        output_summary=(
            str((follow_slim or {}).get("conclusion") or report.output_summary())
        ),
        task_id=envelope.task_id,
        expert=expert,
        conversation_id=conversation_id,
        mode=mode,
        latency_ms=elapsed,
        tokens=None,
        tool_calls=len(report.commands),
        status=str((follow_slim or {}).get("status") or report.status),
    )

    if follow_slim is not None:
        if follow_slim.get("verified") is None and verified_payload is not None:
            follow_slim = {
                **follow_slim,
                "verified": {
                    "ok": bool(verified_payload.get("ok")),
                    "issues": list(verified_payload.get("issues") or []),
                },
            }
        return follow_slim

    return slim_dispatch_for_agent(
        {
            "ok": True,
            "status": report.status,
            "taskId": envelope.task_id,
            "expert": expert,
            "report": report.model_dump(),
            "verified": verified_payload,
        }
    )


def envelope_trace() -> str:
    return f"trace_{uuid.uuid4().hex[:12]}"


def send_control(task_id: str, action: str, conversation_id: str) -> dict[str, Any]:
    meta = load_meta(task_id)
    if not meta:
        return {"error": {"code": 404, "message": "任务不存在或已过期"}}
    expert = str(meta.get("expert") or "")
    if not expert:
        return {"error": {"code": 400, "message": "任务缺少 expert"}}
    if action != "approve":
        clear_pending_hitl(conversation_id)
    started = time.perf_counter()
    outcome = resume_via_http(expert, task_id, action)
    etype = str(outcome.get("type") or "failed")
    payload = outcome.get("payload") if isinstance(outcome.get("payload"), dict) else {}
    if etype == "report":
        clear_pending_hitl(conversation_id)
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        emit_agent_task(
            phase="done",
            reason="hitl_resume",
            input_summary=action,
            output_summary=str(payload.get("conclusion") or "")[:400],
            task_id=task_id,
            expert=expert,
            conversation_id=conversation_id,
            latency_ms=elapsed,
        )
        return {
            "decision": action,
            "taskId": task_id,
            "report": payload,
            "conversationId": conversation_id,
            "query": f"[审批{'通过' if action == 'approve' else '拒绝'}]",
            "answer": str(payload.get("conclusion") or ""),
            "steps": [],
            "humanCs": None,
            "requestId": task_id,
        }
    msg = str(payload.get("message") or "失败")
    clear_pending_hitl(conversation_id)
    return {"error": {"code": 500, "message": msg}}


def pending_task_for_conversation(conversation_id: str) -> str | None:
    return get_pending_hitl(conversation_id)
