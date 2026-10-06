"""工具权限与执行上下文。

职责：
- 声明业务权限码与执行模式
- ExecutionContext：服务端可信身份/白名单/权限（模型不可伪造）
- PermissionEngine：白名单 + RBAC 硬边界
- contextvars：Agent 一轮对话内传播当前上下文

高风险人工审批改由 LangGraph HumanInTheLoopMiddleware + checkpointer 承担。
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# 业务权限码（ToolPolicy.permission 与 ExecutionContext.permissions 共用）
# ---------------------------------------------------------------------------

PERM_ORDER_READ = "order:read"
PERM_LOGISTICS_READ = "logistics:read"
PERM_AFTER_SALE_READ = "after_sale:read"
PERM_REFUND_READ = "refund:read"
PERM_REFUND_CREATE = "refund:create"
PERM_INVOICE_READ = "invoice:read"
PERM_INVOICE_DOWNLOAD = "invoice:download"
PERM_CS_ESCALATE = "cs:escalate"

ALL_AGENT_PERMISSIONS: frozenset[str] = frozenset(
    {
        PERM_ORDER_READ,
        PERM_LOGISTICS_READ,
        PERM_AFTER_SALE_READ,
        PERM_REFUND_READ,
        PERM_REFUND_CREATE,
        PERM_INVOICE_READ,
        PERM_INVOICE_DOWNLOAD,
        PERM_CS_ESCALATE,
    }
)


class PermissionDecision(StrEnum):
    """授权决策结果：允许、拒绝、需人工确认。"""

    ALLOW = "allow"
    DENY = "deny"
    CONFIRM = "confirm"


class PermissionMode(StrEnum):
    """执行模式只能由服务端设置，模型参数无权变更。"""

    DEFAULT = "default"
    PLAN = "plan"  # 只允许读，禁止写
    BYPASS_PERMISSIONS = "bypassPermissions"  # 跳过确认（不跳过白名单/RBAC）
    DONT_ASK = "dontAsk"  # 无法请求确认时直接拒绝需确认的操作


@dataclass(frozen=True)
class ExecutionContext:
    """每次调用携带的可信身份与授权上下文。"""

    trace_id: str
    user_id: str
    tenant_id: str
    permissions: frozenset[str]
    allowed_tools: frozenset[str]
    idempotency_key: str | None = None
    mode: PermissionMode = PermissionMode.DEFAULT
    user_query: str = ""
    conversation_id: str = ""


class PolicyDenied(Exception):
    """策略拒绝：白名单、参数、权限、预检不满足。"""

    def __init__(self, code: str, message: str, content: Any | None = None):
        super().__init__(message)
        self.code = code
        self.content = content if content is not None else {"message": message}


class _ToolPolicyLike(Protocol):
    permission: str
    requires_confirmation: bool


class _ToolLike(Protocol):
    name: str
    policy: _ToolPolicyLike


class PermissionEngine:
    """调用前授权：白名单与业务权限均为不可跳过的硬边界。"""

    def decide(self, tool: _ToolLike, ctx: ExecutionContext) -> PermissionDecision:
        if tool.name not in ctx.allowed_tools:
            return PermissionDecision.DENY
        if tool.policy.permission not in ctx.permissions:
            return PermissionDecision.DENY
        if tool.policy.requires_confirmation and ctx.mode is PermissionMode.DEFAULT:
            return PermissionDecision.CONFIRM
        return PermissionDecision.ALLOW


_current_ctx: ContextVar[ExecutionContext | None] = ContextVar(
    "tool_execution_context",
    default=None,
)


def get_execution_context() -> ExecutionContext | None:
    return _current_ctx.get()


def set_execution_context(ctx: ExecutionContext) -> Token[ExecutionContext | None]:
    return _current_ctx.set(ctx)


def reset_execution_context(token: Token[ExecutionContext | None]) -> None:
    _current_ctx.reset(token)


def build_default_context(
    *,
    allowed_tools: frozenset[str],
    permissions: frozenset[str] | None = None,
    user_id: str = "anonymous",
    tenant_id: str = "default",
    trace_id: str | None = None,
    mode: PermissionMode = PermissionMode.DEFAULT,
    conversation_id: str = "",
) -> ExecutionContext:
    """构造 Agent 默认执行上下文（全量业务权限 + 工具白名单）。"""
    return ExecutionContext(
        trace_id=trace_id or f"trace_{uuid.uuid4().hex[:12]}",
        user_id=user_id,
        tenant_id=tenant_id,
        permissions=permissions if permissions is not None else ALL_AGENT_PERMISSIONS,
        allowed_tools=allowed_tools,
        mode=mode,
        conversation_id=conversation_id,
    )


_permission_engine = PermissionEngine()


def get_permission_engine() -> PermissionEngine:
    return _permission_engine
