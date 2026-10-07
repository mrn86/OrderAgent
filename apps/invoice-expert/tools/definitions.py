"""发票工具创建：参数契约、handler、ToolDefinition。

只在发票专家进程内安装，不并入共享业务注册表。
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import Field, field_validator, model_validator

from app.core.agent.tools.governance import (
    Effect,
    Risk,
    StrictArgs,
    ToolDefinition,
    ToolPolicy,
)
from access.config import PERM_CS_ESCALATE, PERM_INVOICE_DOWNLOAD, PERM_INVOICE_READ
from app.core.agent.tools.registry import slim_invoice_for_agent
from app.core.config import get_settings
from app.service import invoices as invoice_service

INVOICE_ID_PATTERN = r"^INV\d{8,}$"
ORDER_ID_PATTERN = r"^O\d{8,}$"
ORDER_NO_PATTERN = r"^\d{16}$"

INVOICE_READ_POLICY = ToolPolicy(
    effect=Effect.READ,
    risk=Risk.LOW,
    permission=PERM_INVOICE_READ,
    timeout_seconds=5.0,
    max_retries=1,
    idempotent=True,
)
DOWNLOAD_POLICY = ToolPolicy(
    effect=Effect.READ,
    risk=Risk.LOW,
    permission=PERM_INVOICE_DOWNLOAD,
    timeout_seconds=5.0,
    max_retries=1,
    idempotent=True,
)
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


class ListInvoicesByOrderArgs(StrictArgs):
    """按订单号或订单 ID 二选一查发票列表。"""

    order_no: Optional[str] = Field(default=None, pattern=ORDER_NO_PATTERN)
    order_id: Optional[str] = Field(default=None, pattern=ORDER_ID_PATTERN)

    @field_validator("order_no", "order_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: Any) -> Any:
        return _empty_to_none(value)

    @model_validator(mode="after")
    def require_one_identifier(self) -> ListInvoicesByOrderArgs:
        if not self.order_no and not self.order_id:
            raise ValueError("必须提供 order_no 或 order_id 之一")
        return self


class GetInvoiceArgs(StrictArgs):
    """发票详情：发票 ID 必填。"""

    invoice_id: str = Field(pattern=INVOICE_ID_PATTERN)


class CreateInvoiceDownloadUrlsArgs(StrictArgs):
    """发票下载链接：types 为逗号分隔格式列表；expire_seconds 限制链接有效期。"""

    invoice_id: str = Field(pattern=INVOICE_ID_PATTERN)
    types: str = Field(default="PDF,OFD", max_length=64)
    expire_seconds: int = Field(default=1800, ge=60, le=86400)

    @field_validator("types", mode="before")
    @classmethod
    def coerce_types(cls, value: Any) -> Any:
        if isinstance(value, list):
            return ",".join(str(x).strip() for x in value if str(x).strip()) or "PDF,OFD"
        if isinstance(value, str):
            return value.strip() or "PDF,OFD"
        return value


class EscalateToHumanCsArgs(StrictArgs):
    """转人工：reason 写入前端 humanCs 载荷，供用户理解转接原因。"""

    reason: str = Field(default="无法自动处理", min_length=1, max_length=200)


def _get_invoice(args: GetInvoiceArgs) -> dict[str, Any]:
    raw = invoice_service.get_invoice(args.invoice_id)
    if isinstance(raw, dict):
        return slim_invoice_for_agent(raw)
    return raw


def _list_invoices_by_order(args: ListInvoicesByOrderArgs) -> dict[str, Any]:
    return invoice_service.list_by_order(order_id=args.order_id, order_no=args.order_no)


def _create_invoice_download_urls(args: CreateInvoiceDownloadUrlsArgs) -> dict[str, Any]:
    type_list = [t.strip().upper() for t in (args.types or "PDF").split(",") if t.strip()]
    return invoice_service.create_download_urls(
        args.invoice_id,
        types=type_list or ["PDF"],
        expire_seconds=args.expire_seconds,
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


INVOICE_TOOL_DEFINITIONS: list[ToolDefinition] = [
    ToolDefinition(
        name="get_invoice",
        description=(
            "按发票 ID 查看发票详情。用户已给出 INV 开头的发票 ID 时必须用本工具，"
            "不要用 list_invoices_by_order，也不要把发票 ID 当成订单号。"
            "返回不含发信动作；禁止编造「已发送邮箱/短信」等未实现能力。"
        ),
        parameters_model=GetInvoiceArgs,
        policy=INVOICE_READ_POLICY,
        handler=_get_invoice,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name="list_invoices_by_order",
        description=(
            "仅在用户给的是订单号/订单 ID、还没有发票 ID 时，按订单查发票列表。"
            "参数只能是 order_no 或 order_id；禁止传入发票 ID（INV…）。"
        ),
        parameters_model=ListInvoicesByOrderArgs,
        policy=INVOICE_READ_POLICY,
        handler=_list_invoices_by_order,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name="create_invoice_download_urls",
        description=(
            "按发票 ID 生成下载链接（仅生成链接，不发送邮件）。"
            "已有 INV 开头的发票 ID 时直接调用，不必先列表。"
            "types 为 PDF/OFD/XML，逗号分隔，大小写均可；未指定用 PDF,OFD。"
            "一次成功后立即把链接交给用户，禁止重复调用本工具；禁止声称已发送邮箱。"
        ),
        parameters_model=CreateInvoiceDownloadUrlsArgs,
        policy=DOWNLOAD_POLICY,
        handler=_create_invoice_download_urls,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name="escalate_to_human_cs",
        description=(
            "无法回答或超出发票查询/下载能力时，转人工客服兜底，返回人工客服链接。"
            "业务范围内信息不全时应先追问或调用查询类工具，不要用本工具。"
        ),
        parameters_model=EscalateToHumanCsArgs,
        policy=ESCALATE_POLICY,
        handler=_escalate_to_human_cs,  # type: ignore[arg-type]
    ),
]


def register_invoice_tools() -> None:
    from app.core.agent.tools import install_process_tools
    from app.core.agent.tools.report import build_submit_report_definition

    install_process_tools(
        [*INVOICE_TOOL_DEFINITIONS, build_submit_report_definition(PERM_CS_ESCALATE)]
    )
