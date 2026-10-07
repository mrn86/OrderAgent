"""agent_task 审计：创建原因、输入/输出摘要、耗时、失败原因、资源。"""

from __future__ import annotations

from typing import Any

from app.core.audit.redact import redact_value
from app.core.audit.request_id import ensure_audit_request_id, get_audit_request_id, get_trace_id
from app.core.audit.schema import utc_now_iso
from app.core.audit.sink import emit_record
from app.core.config import get_settings


def build_agent_task_record(
    *,
    phase: str,
    reason: str,
    input_summary: str,
    output_summary: str | None = None,
    failure_reason: str | None = None,
    task_id: str,
    expert: str,
    conversation_id: str | None,
    mode: str | None = None,
    latency_ms: float | None = None,
    tokens: dict[str, Any] | None = None,
    tool_calls: int | None = None,
    redis_wait_ms: float | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    return {
        "kind": "agent_task",
        "audited_at": utc_now_iso(),
        "audit_request_id": get_audit_request_id() or ensure_audit_request_id(),
        "trace_id": get_trace_id() or get_audit_request_id(),
        "agent_id": settings.agent_id,
        "agent_name": settings.agent_name,
        "agent_role": settings.agent_role,
        "phase": phase,
        "reason": reason,
        "input_summary": redact_value(input_summary),
        "output_summary": redact_value(output_summary) if output_summary else None,
        "failure_reason": failure_reason,
        "task_id": task_id,
        "expert": expert,
        "conversation_id": conversation_id,
        "mode": mode,
        "latency": {"e2e_ms": latency_ms} if latency_ms is not None else {},
        "resources": {
            "tokens": tokens,
            "tool_calls": tool_calls,
            "redis_wait_ms": redis_wait_ms,
        },
        "status": status or phase,
    }


def emit_agent_task(**kwargs: Any) -> None:
    emit_record(build_agent_task_record(**kwargs))
