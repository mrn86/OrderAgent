"""LangChain Agent 工具定义（带治理门禁与权限过滤）。

每个工具对应一类业务查询能力，内部委托 app.service.*。
工具返回 JSON 字符串，便于模型阅读与前端步骤展示。
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool

from app.core.agent.tools.governance import (
    Effect,
    Risk,
    ToolDefinition,
    invoke_tool,
    is_tool_allowed,
)
from app.core.agent.tools.permissions import (
    ExecutionContext,
    build_default_context,
    get_execution_context,
)
# 转人工本身是高风险写，但不应再套一层 HITL 审批卡
_HITL_EXCLUDE = frozenset({"escalate_to_human_cs", "submit_expert_report"})
# 本进程独占工具。未安装时没有业务工具。
_PROCESS_TOOLS: list[ToolDefinition] | None = None


def install_process_tools(definitions: list[ToolDefinition]) -> None:
    """本进程只使用这份工具列表。"""
    global _PROCESS_TOOLS
    _PROCESS_TOOLS = list(definitions)
    from app.core.context.compression import reset_write_tool_names

    reset_write_tool_names()


def all_tool_definitions() -> list:
    if _PROCESS_TOOLS is None:
        return []
    return list(_PROCESS_TOOLS)


def resolve_execution_context(ctx: ExecutionContext | None = None) -> ExecutionContext:
    """解析执行上下文：显式传入 > contextvar > 当前角色默认白名单。"""
    if ctx is not None:
        return ctx
    current = get_execution_context()
    if current is not None:
        return current
    from app.core.agent.profiles import current_profile

    profile = current_profile()
    return build_default_context(
        allowed_tools=profile.tools,
        permissions=profile.permissions,
    )


def _to_langchain_tool(definition: ToolDefinition) -> StructuredTool:
    """将 ToolDefinition 导出为 LangChain StructuredTool。"""

    def _run(**kwargs: Any) -> str:
        # 运行时再取一次 contextvar，保证 Agent 轮次内权限生效
        return invoke_tool(definition, kwargs, ctx=resolve_execution_context())

    return StructuredTool.from_function(
        func=_run,
        name=definition.name,
        description=definition.description,
        args_schema=definition.parameters_model,
    )


def get_agent_tools(ctx: ExecutionContext | None = None) -> list[StructuredTool]:
    """返回当前上下文允许的 LangChain 工具列表（白名单 + RBAC 过滤）。"""
    resolved = resolve_execution_context(ctx)
    return [
        _to_langchain_tool(item)
        for item in all_tool_definitions()
        if is_tool_allowed(item, resolved)
    ]


def requires_hitl(definition: ToolDefinition) -> bool:
    """高风险写工具需 HITL；转人工工具除外。"""
    if definition.name in _HITL_EXCLUDE:
        return False
    policy = definition.policy
    return policy.risk is Risk.HIGH and policy.effect is Effect.WRITE


def hitl_interrupt_on() -> dict[str, dict[str, Any]]:
    """按 ToolPolicy.risk/effect 生成 HumanInTheLoopMiddleware.interrupt_on。"""
    return {
        item.name: {
            "allowed_decisions": ["approve", "reject"],
            "description": _hitl_description_factory,
        }
        for item in all_tool_definitions()
        if requires_hitl(item)
    }


def format_hitl_summary(tool_name: str, arguments: dict[str, Any] | None = None) -> str:
    """给用户看的审批摘要：业务语义，不含工具名与原始 JSON 参数。"""
    args = arguments or {}
    if tool_name == "create_refund":
        parts: list[str] = []
        order = args.get("order_no") or args.get("order_id")
        if order:
            parts.append(f"订单 {order}")
        amount = args.get("amount")
        if isinstance(amount, (int, float)):
            parts.append(f"金额 {amount / 100:.2f} 元")
        reason = str(args.get("reason") or "").strip()
        if reason:
            parts.append(f"原因「{reason}」")
        return "申请退款" + (f"：{' · '.join(parts)}" if parts else "")
    return "高风险操作待确认"


def _hitl_description_factory(tool_call: dict[str, Any], state: Any, runtime: Any) -> str:
    del state, runtime
    name = str(tool_call.get("name") or "")
    args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {}
    return format_hitl_summary(name, args)
