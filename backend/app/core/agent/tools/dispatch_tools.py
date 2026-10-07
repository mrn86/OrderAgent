"""路由专用：派发订单/物流/发票专家（Redis 总线，非 HTTP）。"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.core.agent.dispatch import dispatch_expert
from app.core.agent.profiles import DISPATCH_INVOICE, DISPATCH_LOGISTICS, DISPATCH_ORDER
from app.core.agent.tools.governance import Effect, Risk, StrictArgs, ToolDefinition, ToolPolicy
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
            "返回业务摘要：conclusion（对用户结论）、status、risks、unresolved、verified.issues。"
            "用 conclusion 写最终答复，禁止向用户粘贴 JSON 或工具原始字段。"
            "若 status=need_hitl，立即停止并向用户转达审批，不要再调工具。"
        ),
        parameters_model=DispatchExpertArgs,
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
        policy=DISPATCH_POLICY,
        handler=_dispatch_invoice,  # type: ignore[arg-type]
    ),
]
