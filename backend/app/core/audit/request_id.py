"""请求级 audit_request_id / trace_id（网关生成，Agent 轮次回写）。"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_audit_request_id: ContextVar[str | None] = ContextVar("audit_request_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("audit_trace_id", default=None)


def get_audit_request_id() -> str | None:
    return _audit_request_id.get()


def get_trace_id() -> str | None:
    return _trace_id.get()


def set_audit_ids(audit_request_id: str, trace_id: str | None = None) -> None:
    _audit_request_id.set(audit_request_id)
    _trace_id.set(trace_id or audit_request_id)


def ensure_audit_request_id(*, x_request_id: str | None = None) -> str:
    """网关入口：若尚未生成则创建 audit_request_id。

    trace_id 默认等于 audit_request_id；若带 X-Request-Id 则 trace_id 用该头。
    """
    current = _audit_request_id.get()
    if current:
        if x_request_id and x_request_id.strip() and not _trace_id.get():
            _trace_id.set(x_request_id.strip())
        return current

    audit_request_id = f"ar_{uuid.uuid4().hex[:16]}"
    header = (x_request_id or "").strip()
    trace_id = header or audit_request_id
    set_audit_ids(audit_request_id, trace_id)
    return audit_request_id
