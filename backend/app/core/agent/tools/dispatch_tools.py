"""路由专用：派发订单/物流/发票专家（Redis 总线，非 HTTP）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field

from app.core.agent.dispatch import dispatch_expert
from app.core.agent.profiles import DISPATCH_INVOICE, DISPATCH_LOGISTICS, DISPATCH_ORDER
from app.core.agent.protocol import ExpertName, ReportStatus
from app.core.agent.tools.governance import (
    Effect,
    Risk,
    StrictArgs,
    StrictResult,
    ToolDefinition,
    ToolPolicy,
)
from app.core.agent.tools.permissions import PERM_CS_ESCALATE, get_execution_context

DISPATCH_POLICY = ToolPolicy(
    effect=Effect.READ,
    risk=Risk.LOW,
    permission=PERM_CS_ESCALATE,
    timeout_seconds=180.0,
    max_retries=0,
    idempotent=False,
)


class DispatchExpertArgs(StrictArgs):
    instruction: str = Field(..., min_length=1, max_length=2000)
    reason: str = Field(..., min_length=2, max_length=200)
    constraints: str = Field(default="", max_length=1000)


class _DispatchPart(StrictResult):
    model_config = ConfigDict(extra="forbid")


class DispatchVerified(_DispatchPart):
    ok: bool
    issues: list[str] = Field(default_factory=list)


class DispatchApproval(_DispatchPart):
    requestId: str = ""
    tool: str = ""
    summary: str = ""
    conversationId: str = ""
    taskId: str = ""
    args: dict[str, Any] = Field(default_factory=dict)


class DispatchExpertResult(StrictResult):
    """三个派发工具的共同返回：只保留业务摘要，拒绝未声明字段。"""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    status: ReportStatus = "failed"
    taskId: str = ""
    expert: ExpertName | Literal[""] = ""
    conclusion: str = ""
    risks: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    verified: DispatchVerified | None = None
    message: str = ""
    approvalRequired: DispatchApproval | None = None


def _ctx_ids() -> tuple[str, str]:
    ctx = get_execution_context()
    cid = (ctx.conversation_id if ctx else "") or ""
    uid = (ctx.user_id if ctx else "") or "anonymous"
    return cid, uid


def _dispatch_order(args: DispatchExpertArgs) -> dict[str, Any]:
    cid, uid = _ctx_ids()
    return dispatch_expert(
        expert="order",
        instruction=args.instruction,
        reason=args.reason,
        conversation_id=cid,
        user_id=uid,
        constraints=args.constraints,
    )


def _dispatch_logistics(args: DispatchExpertArgs) -> dict[str, Any]:
    cid, uid = _ctx_ids()
    return dispatch_expert(
        expert="logistics",
        instruction=args.instruction,
        reason=args.reason,
        conversation_id=cid,
        user_id=uid,
        constraints=args.constraints,
    )


def _dispatch_invoice(args: DispatchExpertArgs) -> dict[str, Any]:
    cid, uid = _ctx_ids()
    return dispatch_expert(
        expert="invoice",
        instruction=args.instruction,
        reason=args.reason,
        conversation_id=cid,
        user_id=uid,
        constraints=args.constraints,
    )


DISPATCH_DEFINITIONS: list[ToolDefinition] = [
    ToolDefinition(
        name=DISPATCH_ORDER,
        description=(
            "将订单/售后/退款问题指派给订单专家（独立进程）。"
            "不处理物流轨迹；物流请用 dispatch_logistics_expert。"
            "instruction 写清用户问题与已知订单号；reason 写指派原因。"
            "用 conclusion 写最终答复，禁止向用户粘贴 JSON 或工具原始字段。"
            "若 status=need_hitl，立即停止并向用户转达审批，不要再调工具。"
        ),
        parameters_model=DispatchExpertArgs,
        result_model=DispatchExpertResult,
        policy=DISPATCH_POLICY,
        handler=_dispatch_order,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name=DISPATCH_LOGISTICS,
        description=(
            "将物流轨迹/运单/时效预测问题指派给物流专家（独立进程）。"
            "instruction 写清订单号或运单号；reason 写指派原因。"
            "禁止把订单专家或发票专家的结论当作物流事实写入 instruction。"
            "若 status=need_hitl，立即停止。"
        ),
        parameters_model=DispatchExpertArgs,
        result_model=DispatchExpertResult,
        policy=DISPATCH_POLICY,
        handler=_dispatch_logistics,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name=DISPATCH_INVOICE,
        description=(
            "将发票查询/下载问题指派给发票专家（独立进程）。"
            "instruction 写清发票 ID 或订单号；reason 写指派原因。"
            "禁止把订单专家的结论当作发票事实写入 instruction。"
            "若 status=need_hitl，立即停止。"
        ),
        parameters_model=DispatchExpertArgs,
        result_model=DispatchExpertResult,
        policy=DISPATCH_POLICY,
        handler=_dispatch_invoice,  # type: ignore[arg-type]
    ),
]
