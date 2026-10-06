"""组装 gateway / agent_turn JSON。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping

from app.core.audit.redact import redact_value
from app.core.config import get_settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def token_fingerprint(token: str | None) -> str | None:
    if not token:
        return None
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:8]


def prompt_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def truncate_model_result(text: str | None) -> str | None:
    if text is None:
        return None
    settings = get_settings()
    max_chars = max(0, int(settings.audit_model_result_max_chars))
    redacted = redact_value(text)
    if len(redacted) <= max_chars:
        return redacted
    return redacted[:max_chars] + "[truncated]"


def build_agent_turn_record(session_data: Mapping[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    tools = []
    for item in session_data.get("tools") or []:
        tools.append(
            {
                "name": item.get("name"),
                "arguments": redact_value(item.get("arguments") or {}),
                "ok": item.get("ok"),
                "error_code": item.get("error_code"),
                "model": item.get("model"),
            }
        )

    tokens = session_data.get("tokens")
    if isinstance(tokens, dict) and tokens.get("total") is not None:
        budget = int(settings.audit_token_budget)
        total = int(tokens["total"])
        tokens = {
            "input": int(tokens.get("input") or 0),
            "output": int(tokens.get("output") or 0),
            "total": total,
            "remaining_budget": max(0, budget - total),
        }
    else:
        tokens = None

    return {
        "kind": "agent_turn",
        "audited_at": utc_now_iso(),
        "audit_request_id": session_data["audit_request_id"],
        "trace_id": session_data.get("trace_id") or session_data["audit_request_id"],
        "user_id": session_data.get("user_id"),
        "conversation_id": session_data.get("conversation_id"),
        "agent_id": settings.agent_id,
        "agent_name": settings.agent_name,
        "latency": session_data.get("latency") or {},
        "prompt": session_data.get("prompt"),
        "model": session_data.get("model"),
        "model_calls": session_data.get("model_calls") or [],
        "tools": tools,
        "model_result": truncate_model_result(session_data.get("model_result")),
        "agent_rounds": session_data.get("agent_rounds") or 0,
        "tokens": tokens,
        "status": session_data.get("status") or "done",
    }


def build_gateway_record(
    *,
    audit_request_id: str,
    trace_id: str | None,
    path: str,
    method: str,
    auth_ok: bool,
    token: str | None,
    gateway_rate_limited: bool,
    retry_after: int | None,
    status_code: int | None,
    conversation_id: str | None = None,
    user_id: str | None = None,
    model_fallback: bool | None = None,
    model_rate_limited: bool | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    return {
        "kind": "gateway",
        "audited_at": utc_now_iso(),
        "audit_request_id": audit_request_id,
        "trace_id": trace_id or audit_request_id,
        "agent_id": settings.agent_id,
        "agent_name": settings.agent_name,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "path": path,
        "method": method,
        "auth": {
            "ok": auth_ok,
            "scheme": "bearer",
            "token_fingerprint": token_fingerprint(token) if auth_ok else None,
        },
        "gateway_rate_limited": gateway_rate_limited,
        "retry_after": retry_after,
        "model_fallback": model_fallback,
        "model_rate_limited": model_rate_limited,
        "status_code": status_code,
    }
