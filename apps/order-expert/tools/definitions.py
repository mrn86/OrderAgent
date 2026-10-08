"""订单工具：本地治理 Spec + MCP 发现装配；escalate/report 仍本地。"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from access.config import (
    PERM_AFTER_SALE_READ,
    PERM_CS_ESCALATE,
    PERM_ORDER_READ,
    PERM_REFUND_CREATE,
    PERM_REFUND_READ,
)
from app.core.agent.tools.governance import (
    Effect,
    Risk,
    StrictArgs,
    ToolDefinition,
    ToolPolicy,
)
from app.core.agent.tools.mcp_assemble import ToolSpec, assemble_mcp_tool_definitions
from app.core.config import get_settings


def _read_policy(permission: str) -> ToolPolicy:
    return ToolPolicy(
        effect=Effect.READ,
        risk=Risk.LOW,
        permission=permission,
        timeout_seconds=5.0,
        max_retries=1,
        idempotent=True,
    )


ORDER_READ_POLICY = _read_policy(PERM_ORDER_READ)
AFTER_SALE_READ_POLICY = _read_policy(PERM_AFTER_SALE_READ)
REFUND_READ_POLICY = _read_policy(PERM_REFUND_READ)
ESCALATE_POLICY = ToolPolicy(
    effect=Effect.WRITE,
    risk=Risk.HIGH,
    permission=PERM_CS_ESCALATE,
    timeout_seconds=3.0,
    max_retries=0,
    idempotent=True,
)
CREATE_REFUND_POLICY = ToolPolicy(
    effect=Effect.WRITE,
    risk=Risk.HIGH,
    permission=PERM_REFUND_CREATE,
    timeout_seconds=5.0,
    max_retries=0,
    idempotent=True,
)


class EscalateToHumanCsArgs(StrictArgs):
    """转人工：reason 写入前端 humanCs 载荷，供用户理解转接原因。"""

    reason: str = Field(default="无法自动处理", min_length=1, max_length=200)


def slim_order_list_for_agent(payload: dict[str, Any]) -> dict[str, Any]:
    """列表给模型看短摘要，避免模型觉得还要逐笔 get_order_detail 而空转。"""
    if not isinstance(payload, dict) or not isinstance(payload.get("list"), list):
        return payload
    slim_rows: list[dict[str, Any]] = []
    for item in payload["list"]:
        if not isinstance(item, dict):
            slim_rows.append(item)
            continue
        items = item.get("items") or []
        names = [i.get("spuName") for i in items if isinstance(i, dict) and i.get("spuName")]
        slim_rows.append(
            {
                "orderId": item.get("orderId"),
                "orderNo": item.get("orderNo"),
                "status": item.get("status"),
                "statusText": item.get("statusText"),
                "createdAt": item.get("createdAt"),
                "payAmount": item.get("payAmount"),
                "itemCount": item.get("itemCount", len(items)),
                "itemNames": names[:3],
            }
        )
    out = dict(payload)
    out["list"] = slim_rows
    return out


def _escalate_to_human_cs(args: EscalateToHumanCsArgs) -> dict[str, Any]:
    settings = get_settings()
    return {
        "needHuman": True,
        "reason": args.reason,
        "csName": "人工客服",
        "csUrl": settings.human_cs_url,
        "guide": f"如需进一步帮助，请联系人工客服：{settings.human_cs_url}",
    }


ORDER_MCP_SPECS: list[ToolSpec] = [
    ToolSpec("query_orders", ORDER_READ_POLICY, postprocess=slim_order_list_for_agent),
    ToolSpec("get_order_detail", ORDER_READ_POLICY),
    ToolSpec("get_order_by_no", ORDER_READ_POLICY),
    ToolSpec("list_after_sales", AFTER_SALE_READ_POLICY),
    ToolSpec("get_after_sale_detail", AFTER_SALE_READ_POLICY),
    ToolSpec("get_after_sale_progress", AFTER_SALE_READ_POLICY),
    ToolSpec("list_refunds", REFUND_READ_POLICY),
    ToolSpec("get_refund_detail", REFUND_READ_POLICY),
    ToolSpec("get_refund_progress", REFUND_READ_POLICY),
    ToolSpec("create_refund", CREATE_REFUND_POLICY),
]

ESCALATE_TOOL = ToolDefinition(
    name="escalate_to_human_cs",
    description=(
        "无法回答或超出订单/售后/退款能力时，转人工客服兜底，返回人工客服链接。"
        "业务范围内信息不全时应先追问或调用查询类工具，不要用本工具。"
    ),
    parameters_model=EscalateToHumanCsArgs,
    policy=ESCALATE_POLICY,
    handler=_escalate_to_human_cs,  # type: ignore[arg-type]
)


def register_order_tools() -> None:
    from app.core.agent.tools import install_process_tools
    from app.core.agent.tools.report import build_submit_report_definition

    defs = assemble_mcp_tool_definitions(ORDER_MCP_SPECS)
    defs.extend([ESCALATE_TOOL, build_submit_report_definition(PERM_CS_ESCALATE)])
    install_process_tools(defs)
