"""物流工具创建：参数契约、handler、ToolDefinition。

只在物流专家进程内安装，不并入共享业务注册表。
不安装订单查询工具，不调用 order service。
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import Field, field_validator

from app.core.agent.tools.governance import (
    Effect,
    Risk,
    StrictArgs,
    ToolDefinition,
    ToolPolicy,
)
from access.config import PERM_CS_ESCALATE, PERM_LOGISTICS_READ
from app.core.config import get_settings
from app.service import logistics as logistics_service

ORDER_NO_PATTERN = r"^\d{16}$"
TRACKING_NO_PATTERN = r"^[A-Za-z0-9]{6,32}$"


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


def _empty_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class GetLogisticsByOrderNoArgs(StrictArgs):
    """按订单号查物流；include_eta 控制是否带时效预测。"""

    order_no: str = Field(pattern=ORDER_NO_PATTERN)
    include_eta: bool = True


class GetLogisticsTrackingArgs(StrictArgs):
    """按运单号查物流；快递公司编码可选。"""

    tracking_no: str = Field(pattern=TRACKING_NO_PATTERN)
    express_company_code: Optional[str] = Field(default=None, max_length=16)
    include_eta: bool = True

    @field_validator("express_company_code", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: Any) -> Any:
        return _empty_to_none(value)


class EscalateToHumanCsArgs(StrictArgs):
    """转人工：reason 写入前端 humanCs 载荷，供用户理解转接原因。"""

    reason: str = Field(default="无法自动处理", min_length=1, max_length=200)


def _get_logistics_by_order_no(args: GetLogisticsByOrderNoArgs) -> dict[str, Any]:
    return logistics_service.get_by_order_no(args.order_no, include_eta=args.include_eta)


def _get_logistics_tracking(args: GetLogisticsTrackingArgs) -> dict[str, Any]:
    return logistics_service.get_by_tracking(
        args.tracking_no,
        express_company_code=args.express_company_code,
        include_eta=args.include_eta,
    )


def _escalate_to_human_cs(args: EscalateToHumanCsArgs) -> dict[str, Any]:
    settings = get_settings()
    return {
        "needHuman": True,
        "reason": args.reason,
        "csName": "人工客服",
        "csUrl": settings.human_cs_url,
        "guide": f"如需进一步帮助，请联系人工客服：{settings.human_cs_url}",
    }


LOGISTICS_TOOL_DEFINITIONS: list[ToolDefinition] = [
    ToolDefinition(
        name="get_logistics_by_order_no",
        description="按订单号查询物流轨迹与时效预测。",
        parameters_model=GetLogisticsByOrderNoArgs,
        policy=LOGISTICS_READ_POLICY,
        handler=_get_logistics_by_order_no,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name="get_logistics_tracking",
        description="按运单号查询物流轨迹。",
        parameters_model=GetLogisticsTrackingArgs,
        policy=LOGISTICS_READ_POLICY,
        handler=_get_logistics_tracking,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name="escalate_to_human_cs",
        description=(
            "无法回答或超出物流能力时，转人工客服兜底，返回人工客服链接。"
            "业务范围内信息不全时应先追问或调用查询类工具，不要用本工具。"
        ),
        parameters_model=EscalateToHumanCsArgs,
        policy=ESCALATE_POLICY,
        handler=_escalate_to_human_cs,  # type: ignore[arg-type]
    ),
]


def register_logistics_tools() -> None:
    from app.core.agent.tools import install_process_tools
    from app.core.agent.tools.report import build_submit_report_definition

    install_process_tools(
        [*LOGISTICS_TOOL_DEFINITIONS, build_submit_report_definition(PERM_CS_ESCALATE)]
    )
