"""订单工具创建：参数契约、handler、ToolDefinition。

只在订单专家进程内安装，不并入共享业务注册表。
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
from access.config import (
    PERM_AFTER_SALE_READ,
    PERM_CS_ESCALATE,
    PERM_ORDER_READ,
    PERM_REFUND_CREATE,
    PERM_REFUND_READ,
)
from app.core.config import get_settings
from app.service import after_sales as after_sale_service
from app.service import orders as order_service
from app.service import refunds as refund_service

ORDER_ID_PATTERN = r"^O\d{8,}$"
ORDER_NO_PATTERN = r"^\d{16}$"
AFTER_SALE_ID_PATTERN = r"^AS\d{8,}$"
REFUND_ID_PATTERN = r"^RF\d{8,}$"


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


def _empty_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class QueryOrdersArgs(StrictArgs):
    """订单列表查询：过滤条件均可选，分页有上下限。"""

    order_no: Optional[str] = Field(default=None, pattern=ORDER_NO_PATTERN)
    order_id: Optional[str] = Field(default=None, pattern=ORDER_ID_PATTERN)
    status: Optional[str] = Field(default=None, max_length=32)
    keyword: Optional[str] = Field(default=None, max_length=100)
    page: int = Field(default=1, ge=1, le=100)
    page_size: int = Field(default=10, ge=1, le=50)

    @field_validator("order_no", "order_id", "status", "keyword", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: Any) -> Any:
        return _empty_to_none(value)


class GetOrderDetailArgs(StrictArgs):
    """按内部订单 ID 查详情。"""

    order_id: str = Field(pattern=ORDER_ID_PATTERN)


class GetOrderByNoArgs(StrictArgs):
    """按对外订单号查详情。"""

    order_no: str = Field(pattern=ORDER_NO_PATTERN)


class ListAfterSalesArgs(StrictArgs):
    """售后列表：订单号 / 订单 ID / 售后单号均可选过滤。"""

    order_no: Optional[str] = Field(default=None, pattern=ORDER_NO_PATTERN)
    order_id: Optional[str] = Field(default=None, pattern=ORDER_ID_PATTERN)
    after_sale_id: Optional[str] = Field(default=None, pattern=AFTER_SALE_ID_PATTERN)

    @field_validator("order_no", "order_id", "after_sale_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: Any) -> Any:
        return _empty_to_none(value)


class GetAfterSaleDetailArgs(StrictArgs):
    """售后详情：售后单号必填。"""

    after_sale_id: str = Field(pattern=AFTER_SALE_ID_PATTERN)


class OrderLookupArgs(StrictArgs):
    """按订单号或订单 ID 二选一。"""

    order_no: Optional[str] = Field(default=None, pattern=ORDER_NO_PATTERN)
    order_id: Optional[str] = Field(default=None, pattern=ORDER_ID_PATTERN)

    @field_validator("order_no", "order_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: Any) -> Any:
        return _empty_to_none(value)

    @model_validator(mode="after")
    def require_one_identifier(self) -> OrderLookupArgs:
        if not self.order_no and not self.order_id:
            raise ValueError("必须提供 order_no 或 order_id 之一")
        return self


class OptionalOrderLookupArgs(StrictArgs):
    """订单过滤可选（无过滤则返回当前数据集全集）。"""

    order_no: Optional[str] = Field(default=None, pattern=ORDER_NO_PATTERN)
    order_id: Optional[str] = Field(default=None, pattern=ORDER_ID_PATTERN)

    @field_validator("order_no", "order_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: Any) -> Any:
        return _empty_to_none(value)


class GetRefundDetailArgs(StrictArgs):
    """退款详情：退款单号必填。"""

    refund_id: str = Field(pattern=REFUND_ID_PATTERN)


class EscalateToHumanCsArgs(StrictArgs):
    """转人工：reason 写入前端 humanCs 载荷，供用户理解转接原因。"""

    reason: str = Field(default="无法自动处理", min_length=1, max_length=200)


class CreateRefundArgs(StrictArgs):
    """发起仅退款：订单标识二选一；amount 单位为分；reason 必填。"""

    order_no: Optional[str] = Field(default=None, pattern=ORDER_NO_PATTERN)
    order_id: Optional[str] = Field(default=None, pattern=ORDER_ID_PATTERN)
    amount: int = Field(
        ...,
        gt=0,
        description="退款金额，单位：分。金额不明时用订单实付 payAmount（分），勿传元。",
    )
    reason: str = Field(
        ...,
        min_length=4,
        max_length=200,
        description="退款原因，不少于4个汉字/字符；须来自用户明确表述，禁止占位或编造。",
    )
    after_sale_id: Optional[str] = Field(default=None, pattern=AFTER_SALE_ID_PATTERN)

    @field_validator("order_no", "order_id", "after_sale_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: Any) -> Any:
        return _empty_to_none(value)

    @model_validator(mode="after")
    def require_one_identifier(self) -> CreateRefundArgs:
        if not self.order_no and not self.order_id:
            raise ValueError("必须提供 order_no 或 order_id 之一")
        return self


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


def _query_orders(args: QueryOrdersArgs) -> dict[str, Any]:
    raw = order_service.list_orders(
        order_no=args.order_no,
        order_id=args.order_id,
        status=args.status,
        keyword=args.keyword,
        page=args.page,
        page_size=args.page_size,
    )
    return slim_order_list_for_agent(raw)


def _get_order_detail(args: GetOrderDetailArgs) -> dict[str, Any]:
    return order_service.get_order_detail(order_id=args.order_id)


def _get_order_by_no(args: GetOrderByNoArgs) -> dict[str, Any]:
    return order_service.get_order_detail(order_no=args.order_no)


def _list_after_sales(args: ListAfterSalesArgs) -> dict[str, Any]:
    return after_sale_service.list_after_sales(
        order_id=args.order_id,
        order_no=args.order_no,
        after_sale_id=args.after_sale_id,
    )


def _get_after_sale_detail(args: GetAfterSaleDetailArgs) -> dict[str, Any]:
    return after_sale_service.get_after_sale_detail(args.after_sale_id)


def _get_after_sale_progress(args: OrderLookupArgs) -> dict[str, Any]:
    return after_sale_service.get_progress(order_id=args.order_id, order_no=args.order_no)


def _list_refunds(args: OptionalOrderLookupArgs) -> dict[str, Any]:
    return refund_service.list_refunds(order_id=args.order_id, order_no=args.order_no)


def _get_refund_detail(args: GetRefundDetailArgs) -> dict[str, Any]:
    return refund_service.get_refund_detail(args.refund_id)


def _get_refund_progress(args: OrderLookupArgs) -> dict[str, Any]:
    return refund_service.get_progress(order_id=args.order_id, order_no=args.order_no)


def _escalate_to_human_cs(args: EscalateToHumanCsArgs) -> dict[str, Any]:
    settings = get_settings()
    return {
        "needHuman": True,
        "reason": args.reason,
        "csName": "人工客服",
        "csUrl": settings.human_cs_url,
        "guide": f"如需进一步帮助，请联系人工客服：{settings.human_cs_url}",
    }


def _create_refund(args: CreateRefundArgs) -> dict[str, Any]:
    return refund_service.create_refund(
        order_id=args.order_id,
        order_no=args.order_no,
        amount=args.amount,
        reason=args.reason,
        after_sale_id=args.after_sale_id,
    )


ORDER_TOOL_DEFINITIONS: list[ToolDefinition] = [
    ToolDefinition(
        name="query_orders",
        description=(
            "查询订单列表；过滤条件均可选，无订单号也可直接调用拉取当前用户订单。"
            "用户说「查看全部订单/我的订单/订单列表」时调用一次即可，用返回的 list 直接作答，"
            "禁止再对每一笔调用详情/物流工具，除非用户明确要某一笔的明细。"
            "同一查询条件成功返回后不要重复调用。"
            "用户说「给我退款/我的订单退款/帮我退款」等且未给订单号时，必须先调用本工具定位订单，"
            "禁止一上来只追问订单号。"
            "仅 1 笔：用其 order_no/order_id 继续后续操作；多笔：列出摘要请用户选择。"
            "用户说「第N笔/第二笔/上一笔/那笔订单」时，同样先取列表再按序号定位，不要因缺订单号就转人工。"
        ),
        parameters_model=QueryOrdersArgs,
        policy=ORDER_READ_POLICY,
        handler=_query_orders,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name="get_order_detail",
        description="按内部订单ID查询订单详情。",
        parameters_model=GetOrderDetailArgs,
        policy=ORDER_READ_POLICY,
        handler=_get_order_detail,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name="get_order_by_no",
        description="按对外订单号查询订单详情。",
        parameters_model=GetOrderByNoArgs,
        policy=ORDER_READ_POLICY,
        handler=_get_order_by_no,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name="list_after_sales",
        description="查询售后单列表。",
        parameters_model=ListAfterSalesArgs,
        policy=AFTER_SALE_READ_POLICY,
        handler=_list_after_sales,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name="get_after_sale_detail",
        description="查询售后详情与完整进度。",
        parameters_model=GetAfterSaleDetailArgs,
        policy=AFTER_SALE_READ_POLICY,
        handler=_get_after_sale_detail,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name="get_after_sale_progress",
        description="按订单查询退货退款进度摘要。",
        parameters_model=OrderLookupArgs,
        policy=AFTER_SALE_READ_POLICY,
        handler=_get_after_sale_progress,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name="list_refunds",
        description="查询退款列表。",
        parameters_model=OptionalOrderLookupArgs,
        policy=REFUND_READ_POLICY,
        handler=_list_refunds,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name="get_refund_detail",
        description="查询退款详情与进度。",
        parameters_model=GetRefundDetailArgs,
        policy=REFUND_READ_POLICY,
        handler=_get_refund_detail,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name="get_refund_progress",
        description="按订单查询退款进度。",
        parameters_model=OrderLookupArgs,
        policy=REFUND_READ_POLICY,
        handler=_get_refund_progress,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name="create_refund",
        description=(
            "为指定订单发起仅退款申请。"
            "调用前须已定位订单（order_no 或 order_id 二选一）；"
            "用户要退款但未提供订单号时，不要直接追问订单号，先调用查询订单列表工具定位后再回来调用本工具。"
            "amount 为整数、单位分（如 29900=299.00 元）；不明时用订单实付 payAmount（分）。"
            "reason 不少于 4 字，须为用户明确提供的退款原因；未说明原因时不要调用，先向用户确认。"
            "禁止空原因、占位原因或编造原因。"
        ),
        parameters_model=CreateRefundArgs,
        policy=CREATE_REFUND_POLICY,
        handler=_create_refund,  # type: ignore[arg-type]
    ),
    ToolDefinition(
        name="escalate_to_human_cs",
        description=(
            "无法回答或超出订单/售后/退款能力时，转人工客服兜底，返回人工客服链接。"
            "业务范围内信息不全时应先追问或调用查询类工具，不要用本工具。"
        ),
        parameters_model=EscalateToHumanCsArgs,
        policy=ESCALATE_POLICY,
        handler=_escalate_to_human_cs,  # type: ignore[arg-type]
    ),
]


def register_order_tools() -> None:
    from app.core.agent.tools import install_process_tools
    from app.core.agent.tools.report import build_submit_report_definition

    install_process_tools(
        [*ORDER_TOOL_DEFINITIONS, build_submit_report_definition(PERM_CS_ESCALATE)]
    )
