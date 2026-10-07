"""A2A AgentExecutor：将 DispatchEnvelope 交给本专家任务执行器。"""

from __future__ import annotations

import logging
from typing import Any

from a2a.helpers import get_data_parts, new_data_part, new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types.a2a_pb2 import TaskState

from app.core.agent.expert_worker import run_expert_task
from app.core.agent.profiles import current_profile
from app.core.agent.protocol import DispatchEnvelope

logger = logging.getLogger(__name__)


def _envelope_from_context(context: RequestContext) -> DispatchEnvelope:
    message = context.message
    if message is not None:
        for item in get_data_parts(message.parts):
            if isinstance(item, dict) and (
                "instruction" in item or "task_id" in item or "taskId" in item
            ):
                normalized = {
                    "task_id": item.get("task_id") or item.get("taskId") or context.task_id,
                    "trace_id": item.get("trace_id")
                    or item.get("traceId")
                    or f"trace_{(context.task_id or 'a2a')[:12]}",
                    "conversation_id": item.get("conversation_id")
                    or item.get("conversationId")
                    or context.context_id
                    or "",
                    "user_id": item.get("user_id") or item.get("userId") or "anonymous",
                    "expert": item.get("expert")
                    or current_profile().expert_name
                    or current_profile().role,
                    "mode": item.get("mode") or "execute",
                    "reason": item.get("reason") or "a2a_dispatch",
                    "input_summary": item.get("input_summary") or item.get("inputSummary") or "",
                    "instruction": item.get("instruction") or context.get_user_input() or "",
                    "constraints": item.get("constraints") or "",
                    "timeout_ms": item.get("timeout_ms") or item.get("timeoutMs") or 120000,
                    "parent_task_id": item.get("parent_task_id") or item.get("parentTaskId"),
                }
                return DispatchEnvelope.model_validate(normalized)
    text = context.get_user_input()
    profile = current_profile()
    expert = profile.expert_name or profile.role
    return DispatchEnvelope(
        task_id=context.task_id or "",
        trace_id=f"trace_{(context.task_id or 'a2a')[:12]}",
        conversation_id=context.context_id or "",
        expert=expert,  # type: ignore[arg-type]
        instruction=text,
        reason="a2a_text",
        input_summary=(text or "")[:240],
    )


class ExpertAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or ""
        context_id = context.context_id or ""
        updater = TaskUpdater(event_queue, task_id, context_id)
        await updater.start_work()
        try:
            envelope = _envelope_from_context(context)
            if not envelope.task_id:
                envelope.task_id = task_id
            outcome = await run_expert_task(envelope)
            etype = str(outcome.get("type") or "failed")
            payload: dict[str, Any] = (
                outcome.get("payload") if isinstance(outcome.get("payload"), dict) else {}
            )
            if etype == "approval_required":
                await updater.add_artifact(
                    [new_data_part(payload, media_type="application/json")],
                    name="approval_required",
                )
                await updater.complete()
                return
            if etype == "report":
                await updater.add_artifact(
                    [new_data_part(payload, media_type="application/json")],
                    name="report",
                )
                await updater.complete()
                return
            msg = str(payload.get("message") or "专家任务失败")
            await updater.add_artifact(
                [new_data_part({"message": msg}, media_type="application/json")],
                name="failed",
            )
            await updater.failed(new_text_message(msg, context_id=context_id, task_id=task_id))
        except Exception as exc:  # noqa: BLE001
            logger.exception("a2a execute failed task_id=%s", task_id)
            await updater.update_status(
                TaskState.TASK_STATE_FAILED,
                message=new_text_message(str(exc), context_id=context_id, task_id=task_id),
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id or "", context.context_id or "")
        await updater.cancel()
