"""LangChain Agent 工具定义（带治理门禁与权限过滤）。

每个工具对应一类业务查询能力，内部委托 app.service.*。
工具返回 JSON 字符串，便于模型阅读与前端步骤展示。
"""

from __future__ import annotations

import json
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
from app.core.agent.profiles import current_profile
from app.core.agent.tools.dispatch_tools import DISPATCH_DEFINITIONS
from app.core.agent.tools.registry import TOOL_DEFINITIONS
from app.core.agent.tools.report import SUBMIT_REPORT_DEFINITION

# 转人工本身是高风险写，但不应再套一层 HITL 审批卡
_HITL_EXCLUDE = frozenset({"escalate_to_human_cs", "submit_expert_report"})


def all_tool_definitions() -> list:
    return [*TOOL_DEFINITIONS, *DISPATCH_DEFINITIONS, SUBMIT_REPORT_DEFINITION]


def resolve_execution_context(ctx: ExecutionContext | None = None) -> ExecutionContext:
    """解析执行上下文：显式传入 > contextvar > 当前角色默认白名单。"""
    if ctx is not None:
        return ctx
    current = get_execution_context()
    if current is not None:
        return current
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


def list_tool_schemas(ctx: ExecutionContext | None = None) -> list[dict[str, Any]]:
    """导出当前上下文下模型可见的工具 Schema。"""
    resolved = resolve_execution_context(ctx)
    return [
        item.to_model_tool()
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
    """审批卡通用摘要。"""
    args = arguments or {}
    if not args:
        return f"高风险写操作：{tool_name}"
    try:
        args_text = json.dumps(args, ensure_ascii=False)
    except Exception:
        args_text = str(args)
    return f"高风险写操作：{tool_name}，参数 {args_text}"


def _hitl_description_factory(tool_call: dict[str, Any], state: Any, runtime: Any) -> str:
    del state, runtime
    name = str(tool_call.get("name") or "")
    args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {}
    return format_hitl_summary(name, args)
