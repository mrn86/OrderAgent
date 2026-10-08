"""物流工具：本地治理 Spec + MCP 发现装配；escalate/report 仍本地。"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from access.config import PERM_CS_ESCALATE, PERM_LOGISTICS_READ
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


LOGISTICS_READ_POLICY = _read_policy(PERM_LOGISTICS_READ)
ESCALATE_POLICY = ToolPolicy(
    effect=Effect.WRITE,
    risk=Risk.HIGH,
    permission=PERM_CS_ESCALATE,
    timeout_seconds=3.0,
    max_retries=0,
    idempotent=True,
)


class EscalateToHumanCsArgs(StrictArgs):
    """转人工：reason 写入前端 humanCs 载荷，供用户理解转接原因。"""

    reason: str = Field(default="无法自动处理", min_length=1, max_length=200)


def _escalate_to_human_cs(args: EscalateToHumanCsArgs) -> dict[str, Any]:
    settings = get_settings()
    return {
        "needHuman": True,
        "reason": args.reason,
        "csName": "人工客服",
        "csUrl": settings.human_cs_url,
        "guide": f"如需进一步帮助，请联系人工客服：{settings.human_cs_url}",
    }


LOGISTICS_MCP_SPECS: list[ToolSpec] = [
    ToolSpec("get_logistics_by_order_no", LOGISTICS_READ_POLICY),
    ToolSpec("get_logistics_tracking", LOGISTICS_READ_POLICY),
]

ESCALATE_TOOL = ToolDefinition(
    name="escalate_to_human_cs",
    description=(
        "无法回答或超出物流能力时，转人工客服兜底，返回人工客服链接。"
        "业务范围内信息不全时应先追问或调用查询类工具，不要用本工具。"
    ),
    parameters_model=EscalateToHumanCsArgs,
    policy=ESCALATE_POLICY,
    handler=_escalate_to_human_cs,  # type: ignore[arg-type]
)


def register_logistics_tools() -> None:
    from app.core.agent.tools import install_process_tools
    from app.core.agent.tools.report import build_submit_report_definition

    defs = assemble_mcp_tool_definitions(LOGISTICS_MCP_SPECS)
    defs.extend([ESCALATE_TOOL, build_submit_report_definition(PERM_CS_ESCALATE)])
    install_process_tools(defs)
