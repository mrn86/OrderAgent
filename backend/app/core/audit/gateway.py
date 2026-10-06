"""网关侧审计发射。"""

from __future__ import annotations

from typing import Any

from app.core.audit.request_id import (
    ensure_audit_request_id,
    get_audit_request_id,
    get_trace_id,
)
from app.core.audit.schema import build_gateway_record
from app.core.audit.session import get_agent_audit_session, get_last_model_flags
from app.core.audit.sink import emit_record


def emit_gateway_audit(
    *,
    path: str,
    method: str,
    auth_ok: bool,
    token: str | None = None,
    gateway_rate_limited: bool = False,
    retry_after: int | None = None,
    status_code: int | None = None,
    conversation_id: str | None = None,
    user_id: str | None = None,
    model_fallback: bool | None = None,
    model_rate_limited: bool | None = None,
    include_model_summary: bool = False,
    x_request_id: str | None = None,
) -> None:
    audit_request_id = get_audit_request_id() or ensure_audit_request_id(
        x_request_id=x_request_id
    )
    if include_model_summary:
        session = get_agent_audit_session()
        if session is not None:
            model_fallback = session.had_fallback()
            model_rate_limited = session.had_rate_limited()
        else:
            flags = get_last_model_flags()
            if flags is not None:
                model_fallback, model_rate_limited = flags
            elif model_fallback is None and model_rate_limited is None:
                model_fallback = False
                model_rate_limited = False

    record = build_gateway_record(
        audit_request_id=audit_request_id,
        trace_id=get_trace_id(),
        path=path,
        method=method,
        auth_ok=auth_ok,
        token=token,
        gateway_rate_limited=gateway_rate_limited,
        retry_after=retry_after,
        status_code=status_code,
        conversation_id=conversation_id,
        user_id=user_id,
        model_fallback=model_fallback,
        model_rate_limited=model_rate_limited,
    )
    emit_record(record)
