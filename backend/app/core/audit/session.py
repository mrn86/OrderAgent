"""Agent 轮次审计收集器。"""

from __future__ import annotations

import time
from contextvars import ContextVar, Token
from typing import Any, Mapping

from app.core.audit.model_meta import extract_usage, parse_model_call_meta
from app.core.audit.request_id import (
    ensure_audit_request_id,
    get_audit_request_id,
    get_trace_id,
)
from app.core.audit.schema import build_agent_turn_record, prompt_hash
from app.core.audit.sink import emit_record

_session_var: ContextVar[AgentAuditSession | None] = ContextVar(
    "agent_audit_session",
    default=None,
)
# finish 后仍可供网关收尾审计读取
_last_model_flags: ContextVar[tuple[bool, bool] | None] = ContextVar(
    "audit_last_model_flags",
    default=None,
)


def get_last_model_flags() -> tuple[bool, bool] | None:
    return _last_model_flags.get()


class AgentAuditSession:
    def __init__(
        self,
        *,
        audit_request_id: str,
        trace_id: str,
        user_id: str | None,
        conversation_id: str | None,
        prompt_type: str | None = None,
        prompt_version: str | None = None,
        prompt_content: str | None = None,
    ) -> None:
        self.audit_request_id = audit_request_id
        self.trace_id = trace_id
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.prompt = None
        if prompt_type and prompt_content is not None:
            self.prompt = {
                "type": prompt_type,
                "version": prompt_version or "unknown",
                "hash": prompt_hash(prompt_content),
            }
        self._started = time.perf_counter()
        self._first_token_at: float | None = None
        self._last_model_end_at: float | None = None
        self._model_calls: list[dict[str, Any]] = []
        self._tools: list[dict[str, Any]] = []
        self._input_tokens = 0
        self._output_tokens = 0
        self._total_tokens = 0
        self._has_usage = False
        self.model_result: str | None = None
        self.status = "done"
        self._last_model_call: dict[str, Any] | None = None

    def mark_first_token(self) -> None:
        if self._first_token_at is None:
            self._first_token_at = time.perf_counter()

    def add_model_message(self, message: Any, *, rate_limited: bool = False) -> None:
        round_index = len(self._model_calls) + 1
        call = parse_model_call_meta(message, round_index=round_index, rate_limited=rate_limited)
        self._model_calls.append(call)
        self._last_model_call = call
        self._last_model_end_at = time.perf_counter()
        usage = extract_usage(message)
        if usage:
            self._has_usage = True
            self._input_tokens += usage["input"]
            self._output_tokens += usage["output"]
            self._total_tokens += usage["total"]

    def add_tool(
        self,
        name: str,
        arguments: Mapping[str, Any] | None,
        *,
        ok: bool,
        error_code: str | None = None,
    ) -> None:
        model_snap = None
        if self._last_model_call:
            model_snap = {
                "requested_group": self._last_model_call.get("requested_group"),
                "resolved_model": self._last_model_call.get("resolved_model"),
                "fallback": self._last_model_call.get("fallback"),
                "rate_limited": self._last_model_call.get("rate_limited"),
            }
        self._tools.append(
            {
                "name": name,
                "arguments": dict(arguments or {}),
                "ok": ok,
                "error_code": error_code,
                "model": model_snap,
            }
        )

    def set_model_result(self, text: str | None) -> None:
        self.model_result = text

    def set_status(self, status: str) -> None:
        self.status = status

    def had_fallback(self) -> bool:
        return any(bool(item.get("fallback")) for item in self._model_calls)

    def had_rate_limited(self) -> bool:
        return any(bool(item.get("rate_limited")) for item in self._model_calls)

    def _latency(self) -> dict[str, float | None]:
        now = time.perf_counter()
        e2e = round((now - self._started) * 1000, 2)
        ttft = None
        gen = None
        if self._first_token_at is not None:
            ttft = round((self._first_token_at - self._started) * 1000, 2)
            end = self._last_model_end_at or now
            gen = round((end - self._first_token_at) * 1000, 2)
        return {"ttft_ms": ttft, "gen_ms": gen, "e2e_ms": e2e}

    def finish(self, *, status: str | None = None, model_result: str | None = None) -> None:
        if status is not None:
            self.status = status
        if model_result is not None:
            self.model_result = model_result
        tokens = None
        if self._has_usage:
            tokens = {
                "input": self._input_tokens,
                "output": self._output_tokens,
                "total": self._total_tokens,
            }
        summary_model = None
        if self._model_calls:
            last = self._model_calls[-1]
            summary_model = {
                "requested_group": last.get("requested_group"),
                "resolved_model": last.get("resolved_model"),
                "model_id": last.get("model_id"),
                "fallback": self.had_fallback(),
                "rate_limited": self.had_rate_limited(),
            }
        record = build_agent_turn_record(
            {
                "audit_request_id": self.audit_request_id,
                "trace_id": self.trace_id,
                "user_id": self.user_id,
                "conversation_id": self.conversation_id,
                "latency": self._latency(),
                "prompt": self.prompt,
                "model": summary_model,
                "model_calls": list(self._model_calls),
                "tools": list(self._tools),
                "model_result": self.model_result,
                "agent_rounds": len(self._model_calls),
                "tokens": tokens,
                "status": self.status,
            }
        )
        _last_model_flags.set((self.had_fallback(), self.had_rate_limited()))
        emit_record(record)


def get_agent_audit_session() -> AgentAuditSession | None:
    return _session_var.get()


def start_agent_audit(
    *,
    user_id: str | None,
    conversation_id: str | None,
    prompt_type: str | None = None,
    prompt_version: str | None = None,
    prompt_content: str | None = None,
) -> tuple[AgentAuditSession, Token[AgentAuditSession | None]]:
    audit_request_id = get_audit_request_id() or ensure_audit_request_id()
    trace_id = get_trace_id() or audit_request_id
    session = AgentAuditSession(
        audit_request_id=audit_request_id,
        trace_id=trace_id,
        user_id=user_id,
        conversation_id=conversation_id,
        prompt_type=prompt_type,
        prompt_version=prompt_version,
        prompt_content=prompt_content,
    )
    token = _session_var.set(session)
    return session, token


def reset_agent_audit(token: Token[AgentAuditSession | None]) -> None:
    _session_var.reset(token)
