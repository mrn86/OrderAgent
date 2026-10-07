"""专家任务执行：供 A2A AgentExecutor 与 HITL resume 调用。"""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

from app.core.agent.a2a_task_registry import ParkedExpertTask, park_task, take_parked
from app.core.agent.bus import save_meta
from app.core.agent.loop import resume_agent_after_decision, stream_agent_loop
from app.core.agent.profiles import current_profile, expert_thread_id
from app.core.agent.protocol import DispatchEnvelope, report_from_answer
from app.core.agent.tools.permissions import build_default_context
from app.core.agent.tools.report import clear_submitted_report, get_submitted_report
from app.core.audit import ensure_audit_request_id, set_audit_ids
from app.core.audit.task import emit_agent_task

logger = logging.getLogger(__name__)

ExpertOutcomeType = Literal["report", "approval_required", "failed"]


def _build_report(
    *,
    envelope: DispatchEnvelope,
    answer: str,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    from app.core.agent.protocol import commands_from_steps, upgrade_report_with_list_steps

    report = get_submitted_report()
    if report is None:
        report = report_from_answer(
            answer, task_id=envelope.task_id, expert=envelope.expert, steps=steps
        )
    else:
        report.task_id = envelope.task_id
        report.expert = envelope.expert
        if not report.commands:
            report.commands = commands_from_steps(steps)
    report = upgrade_report_with_list_steps(report, steps)
    return report.model_dump()


async def run_expert_task(raw: dict[str, Any] | DispatchEnvelope) -> dict[str, Any]:
    """执行专家任务，返回 {type, payload}，不经 Redis 派发。"""
    envelope = (
        raw
        if isinstance(raw, DispatchEnvelope)
        else DispatchEnvelope.model_validate(raw)
    )
    profile = current_profile()
    if profile.expert_name and profile.expert_name != envelope.expert:
        logger.warning("ignore task expert=%s local=%s", envelope.expert, profile.expert_name)
        return {
            "type": "failed",
            "payload": {
                "message": f"专家不匹配：期望 {profile.expert_name}，收到 {envelope.expert}"
            },
        }

    thread_id = expert_thread_id(envelope.conversation_id, profile.agent_id, envelope.task_id)
    set_audit_ids(envelope.trace_id, envelope.trace_id)
    ensure_audit_request_id()
    save_meta(
        envelope.task_id,
        envelope.model_dump() | {"thread_id": thread_id, "status": "running"},
    )
    started = time.perf_counter()
    emit_agent_task(
        phase="started",
        reason=envelope.reason,
        input_summary=envelope.input_summary,
        task_id=envelope.task_id,
        expert=envelope.expert,
        conversation_id=envelope.conversation_id,
        mode=envelope.mode,
    )
    ctx = build_default_context(
        allowed_tools=profile.tools,
        permissions=profile.permissions,
        user_id=envelope.user_id,
        conversation_id=envelope.conversation_id,
        trace_id=envelope.trace_id,
    )
    query = envelope.instruction
    if envelope.constraints:
        query = f"{query}\n\n约束：{envelope.constraints}"
    if envelope.mode != "execute":
        query = f"【模式:{envelope.mode}】{query}"

    clear_submitted_report()
    steps: list[dict[str, Any]] = []
    answer = ""
    try:
        async for event in stream_agent_loop(
            query,
            conversation_id=envelope.conversation_id,
            execution_ctx=ctx,
            thread_id=thread_id,
        ):
            etype = event.get("type")
            if etype == "approval_required":
                payload = {
                    "requestId": envelope.task_id,
                    "tool": event.get("tool"),
                    "args": event.get("args") or {},
                    "summary": event.get("summary") or "",
                    "conversationId": envelope.conversation_id,
                    "taskId": envelope.task_id,
                }
                park_task(
                    envelope.task_id,
                    ParkedExpertTask(
                        envelope=envelope,
                        thread_id=thread_id,
                        execution_ctx=ctx,
                        started=started,
                        approval=payload,
                    ),
                )
                save_meta(
                    envelope.task_id,
                    envelope.model_dump()
                    | {"thread_id": thread_id, "status": "need_hitl", "approval": payload},
                )
                emit_agent_task(
                    phase="approval_required",
                    reason=envelope.reason,
                    input_summary=envelope.input_summary,
                    task_id=envelope.task_id,
                    expert=envelope.expert,
                    conversation_id=envelope.conversation_id,
                    mode=envelope.mode,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                )
                return {"type": "approval_required", "payload": payload}
            if etype == "done":
                answer = str(event.get("answer") or "")
                steps = list(event.get("steps") or [])
            elif etype == "error":
                msg = str(event.get("message") or "专家执行失败")
                emit_agent_task(
                    phase="failed",
                    reason=envelope.reason,
                    input_summary=envelope.input_summary,
                    failure_reason=msg,
                    task_id=envelope.task_id,
                    expert=envelope.expert,
                    conversation_id=envelope.conversation_id,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                )
                return {"type": "failed", "payload": {"message": msg}}

        report = _build_report(envelope=envelope, answer=answer, steps=steps)
        emit_agent_task(
            phase="done",
            reason=envelope.reason,
            input_summary=envelope.input_summary,
            output_summary=str(report.get("conclusion") or "")[:400],
            task_id=envelope.task_id,
            expert=envelope.expert,
            conversation_id=envelope.conversation_id,
            mode=envelope.mode,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            tool_calls=len(report.get("commands") or []),
            status=str(report.get("status") or ""),
        )
        save_meta(
            envelope.task_id,
            envelope.model_dump() | {"thread_id": thread_id, "status": "done"},
        )
        return {"type": "report", "payload": report}
    except Exception as exc:  # noqa: BLE001
        logger.exception("expert task failed task_id=%s", envelope.task_id)
        emit_agent_task(
            phase="failed",
            reason=envelope.reason,
            input_summary=envelope.input_summary,
            failure_reason=str(exc),
            task_id=envelope.task_id,
            expert=envelope.expert,
            conversation_id=envelope.conversation_id,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return {"type": "failed", "payload": {"message": str(exc)}}


async def resume_expert_task(task_id: str, action: str) -> dict[str, Any]:
    """HITL 恢复：approve/reject 后继续跑完并返回 report。"""
    parked = take_parked(task_id)
    if parked is None:
        return {"type": "failed", "payload": {"message": "挂起任务不存在或已过期"}}

    envelope = parked.envelope
    decided = (action or "reject").strip().lower()
    if decided == "cancel":
        decided = "reject"

    resumed = resume_agent_after_decision(
        envelope.conversation_id,
        decided,
        execution_ctx=parked.execution_ctx,
        thread_id=parked.thread_id,
    )
    if "error" in resumed:
        msg = str((resumed.get("error") or {}).get("message") or "审批恢复失败")
        emit_agent_task(
            phase="failed",
            reason=envelope.reason,
            input_summary=envelope.input_summary,
            failure_reason=msg,
            task_id=envelope.task_id,
            expert=envelope.expert,
            conversation_id=envelope.conversation_id,
            latency_ms=round((time.perf_counter() - parked.started) * 1000, 2),
        )
        return {"type": "failed", "payload": {"message": msg}}

    answer = str(resumed.get("answer") or "")
    steps = list(resumed.get("steps") or [])
    report = _build_report(envelope=envelope, answer=answer, steps=steps)
    emit_agent_task(
        phase="done",
        reason="hitl_resume",
        input_summary=decided,
        output_summary=str(report.get("conclusion") or "")[:400],
        task_id=envelope.task_id,
        expert=envelope.expert,
        conversation_id=envelope.conversation_id,
        mode=envelope.mode,
        latency_ms=round((time.perf_counter() - parked.started) * 1000, 2),
        tool_calls=len(report.get("commands") or []),
        status=str(report.get("status") or ""),
    )
    save_meta(
        envelope.task_id,
        envelope.model_dump()
        | {"thread_id": parked.thread_id, "status": "done", "hitl": decided},
    )
    return {"type": "report", "payload": report}
