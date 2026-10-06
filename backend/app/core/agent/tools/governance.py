"""工具治理基础类型（自 docs/tool_governance_demo.py 裁剪落地）。

包含：StrictArgs、StrictResult、Effect/Risk、ToolPolicy、ToolDefinition、脱敏与同步执行封装。
调用分三段：执行前（参数/权限）→ 执行中（超时/重试）→ 执行后（结果验证 + 审计）。
权限决策见 permissions.py；高风险人工审批见 HumanInTheLoopMiddleware。
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.agent.tools.permissions import (
    ExecutionContext,
    PermissionDecision,
    PermissionMode,
    PolicyDenied,
    get_execution_context,
    get_permission_engine,
)

logger = logging.getLogger(__name__)

SENSITIVE_KEY = re.compile(
    r"token|secret|password|authorization|api_?key|credential|cookie|session|private_?key|access_?key",
    re.I,
)


class StrictArgs(BaseModel):
    """所有工具参数的共同边界：拒绝未声明字段，并清理字符串首尾空白。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StrictResult(BaseModel):
    """工具返回值共同边界：必须是对象；未声明字段保留，导出为 JSON 兼容结构。"""

    model_config = ConfigDict(extra="allow")


class Effect(StrEnum):
    """工具副作用分类：用于区分读写语义与重试边界。"""

    READ = "read"
    WRITE = "write"


class Risk(StrEnum):
    """工具风险分级：为审计与后续审批策略提供依据。"""

    LOW = "low"
    HIGH = "high"


@dataclass(frozen=True)
class ToolPolicy:
    """工具治理策略：副作用、风险、权限、确认、超时与重试规则。"""

    effect: Effect
    risk: Risk
    permission: str  # 业务权限码，须出现在 ExecutionContext.permissions
    denied: bool = False
    requires_confirmation: bool = False
    timeout_seconds: float = 5.0
    max_retries: int = 0
    idempotent: bool = True
    enabled: bool = True


Handler = Callable[[StrictArgs], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """工具注册元数据：参数契约、结果契约、治理策略与处理器绑定。"""

    name: str
    description: str
    parameters_model: type[StrictArgs]
    policy: ToolPolicy
    handler: Handler
    result_model: type[BaseModel] = StrictResult

    def to_model_tool(self) -> dict[str, Any]:
        """导出公开描述与参数 Schema，供模型发现可调用工具。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_model.model_json_schema(),
            },
        }


def dumps(data: Any) -> str:
    """工具统一序列化：中文不转义，供模型直接消费。"""
    return json.dumps(data, ensure_ascii=False)


def redact(value: Any) -> Any:
    """递归脱敏敏感字段键名与邮箱。"""
    if isinstance(value, Mapping):
        return {
            key: "***" if SENSITIVE_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "***@***", value)
    return value


def _validation_errors(exc: ValidationError) -> list[dict[str, str]]:
    return [
        {
            "path": ".".join(str(item) for item in err["loc"]),
            "message": err["msg"],
        }
        for err in exc.errors()
    ]


def _error_payload(code: str, message: str, content: Any | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error_code": code,
        "message": message,
        "content": content if content is not None else {"message": message},
    }


def check_permissions(
    definition: ToolDefinition,
    args: StrictArgs,
    ctx: ExecutionContext,
) -> None:
    """调用前门禁：硬拒绝 → plan → 白名单/RBAC → 确认。

    高风险写工具人工审批由 HumanInTheLoopMiddleware 处理。
    不满足时抛出 PolicyDenied（由 invoke_tool 在执行前拦截并转成结构化错误 JSON）。
    """
    policy = definition.policy
    # 1. 硬拒绝
    if policy.denied or not policy.enabled:
        raise PolicyDenied("DENY_RULE", f"工具 {definition.name} 当前不可用")

    # 2. plan 模式禁止写
    if ctx.mode is PermissionMode.PLAN and policy.effect is Effect.WRITE:
        raise PolicyDenied("PLAN_MODE_DENIED", "plan 模式禁止写操作")

    # 3. 白名单 / RBAC
    decision = get_permission_engine().decide(definition, ctx)
    if decision is PermissionDecision.DENY:
        if definition.name not in ctx.allowed_tools:
            raise PolicyDenied(
                "TOOL_NOT_ALLOWED",
                f"工具 {definition.name} 不在本轮白名单",
            )
        raise PolicyDenied(
            "PERMISSION_DENIED",
            f"缺少权限 {policy.permission}",
        )

    # 4. 确认
    if policy.requires_confirmation:
        if ctx.mode is PermissionMode.DONT_ASK:
            raise PolicyDenied("CONFIRMATION_REQUIRED", "当前模式无法请求用户确认")
        if ctx.mode is not PermissionMode.BYPASS_PERMISSIONS:
            # DEFAULT 下 CONFIRM；非 bypass 一律要求确认
            raise PolicyDenied("CONFIRMATION_REQUIRED", f"工具 {definition.name} 需要用户确认")


def is_tool_allowed(definition: ToolDefinition, ctx: ExecutionContext) -> bool:
    """工具是否可向模型暴露（启用 + 白名单 + 权限）。"""
    if definition.policy.denied or not definition.policy.enabled:
        return False
    if ctx.mode is PermissionMode.PLAN and definition.policy.effect is Effect.WRITE:
        return False
    return get_permission_engine().decide(definition, ctx) is not PermissionDecision.DENY


class ResultVerificationError(Exception):
    """执行后校验失败：结果未通过 result_model。"""

    def __init__(self, message: str, content: Any | None = None) -> None:
        super().__init__(message)
        self.code = "INVALID_RESULT"
        self.content = content if content is not None else {"message": message}


@dataclass(frozen=True, slots=True)
class PreparedCall:
    """已通过执行前门禁的调用：解析后的参数与可信上下文。"""

    definition: ToolDefinition
    args: StrictArgs
    ctx: ExecutionContext


def before_tool_call(
    definition: ToolDefinition,
    raw_args: Mapping[str, Any] | None,
    ctx: ExecutionContext | None,
) -> PreparedCall:
    """工具执行前：参数校验 → 上下文检查 → 权限门禁。"""
    try:
        args = definition.parameters_model.model_validate(dict(raw_args or {}))
    except ValidationError as exc:
        raise PolicyDenied(
            "INVALID_ARGUMENT",
            "参数校验失败",
            _validation_errors(exc),
        ) from exc

    if ctx is None:
        raise PolicyDenied("INVALID_CONTEXT", "缺少执行上下文，拒绝调用工具")

    check_permissions(definition, args, ctx)
    return PreparedCall(definition=definition, args=args, ctx=ctx)


def execute_tool(prepared: PreparedCall) -> Any:
    """工具执行中：按策略超时，读工具或幂等写可退避重试。"""
    definition = prepared.definition
    policy = definition.policy
    retries = policy.max_retries if policy.effect is Effect.READ or policy.idempotent else 0
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            # 把当前 ContextVar（含 ExecutionContext）拷进工作线程
            ctx_copy = contextvars.copy_context()
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(ctx_copy.run, definition.handler, prepared.args)
                return future.result(timeout=policy.timeout_seconds)
        except FuturesTimeoutError as exc:
            last_error = TimeoutError(
                f"工具 {definition.name} 执行超时（{policy.timeout_seconds}s）",
            )
            if attempt >= retries:
                raise last_error from exc
        except Exception as exc:  # noqa: BLE001 — 统一包装给模型
            last_error = exc
            if attempt >= retries:
                raise
            time.sleep(0.05 * (2**attempt))

    raise last_error or RuntimeError(f"工具 {definition.name} 执行失败")


def verify_tool_result(definition: ToolDefinition, result: Any) -> dict[str, Any]:
    """用 Pydantic result_model 校验 handler 返回值，再导出 JSON 兼容 dict。"""
    try:
        parsed = definition.result_model.model_validate(result)
        payload = parsed.model_dump(mode="json")
    except ValidationError as exc:
        raise ResultVerificationError("结果校验失败", _validation_errors(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise ResultVerificationError(
            f"工具 {definition.name} 返回值无法序列化为 JSON：{exc}",
        ) from exc
    if not isinstance(payload, dict):
        raise ResultVerificationError(
            f"工具 {definition.name} 返回值必须是对象，实际为 {type(payload).__name__}",
        )
    return payload


def after_tool_call(prepared: PreparedCall, result: Any) -> dict[str, Any]:
    """工具执行后：Pydantic 校验结果，通过后交给模型。"""
    return verify_tool_result(prepared.definition, result)


def _audit_tool_call(
    definition: ToolDefinition,
    *,
    args_map: Mapping[str, Any],
    ctx: ExecutionContext | None,
    ok: bool,
    error_code: str | None,
    started: float,
) -> None:
    del started, ctx
    try:
        from app.core.audit import get_agent_audit_session

        session = get_agent_audit_session()
        if session is not None:
            session.add_tool(
                definition.name,
                args_map,
                ok=ok,
                error_code=error_code,
            )
    except Exception:  # noqa: BLE001
        logger.warning("tool audit attach failed name=%s", definition.name, exc_info=True)


def invoke_tool(
    definition: ToolDefinition,
    raw_args: Mapping[str, Any] | None = None,
    *,
    ctx: ExecutionContext | None = None,
) -> str:
    """同步执行受治理工具：执行前 → 执行中 → 执行后验证；finally 审计。"""
    started = time.perf_counter()
    args_map = dict(raw_args or {})
    ok = False
    error_code: str | None = None
    resolved_ctx = ctx or get_execution_context()

    try:
        # 1. 工具执行前
        prepared = before_tool_call(definition, args_map, resolved_ctx)

        # 2. 工具执行中
        raw_result = execute_tool(prepared)

        # 3. 工具执行后（验证）
        content = after_tool_call(prepared, raw_result)
        ok = True
        # 成功时直接返回业务 JSON，保持与旧工具及 escalate/csUrl 解析兼容
        return dumps(content)
    except PolicyDenied as exc:
        error_code = exc.code
        return dumps(_error_payload(exc.code, str(exc), exc.content))
    except TimeoutError as exc:
        error_code = "TIMEOUT"
        return dumps(_error_payload(error_code, str(exc)))
    except ResultVerificationError as exc:
        error_code = exc.code
        return dumps(_error_payload(error_code, str(exc), exc.content))
    except Exception as exc:  # noqa: BLE001 — 统一包装给模型
        error_code = "HANDLER_ERROR"
        return dumps(
            _error_payload(
                error_code,
                f"工具 {definition.name} 执行失败：{exc}",
            )
        )
    finally:
        _audit_tool_call(
            definition,
            args_map=args_map,
            ctx=resolved_ctx,
            ok=ok,
            error_code=error_code,
            started=started,
        )
