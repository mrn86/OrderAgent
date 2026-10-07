"""业务工具注册表：参数契约 + handler + ToolDefinition。

结构：
1. 标识正则 / 复用策略常量
2. StrictArgs 参数模型（供模型 Schema 与运行时校验）
3. handler：薄封装，委托 app.service.*
4. TOOL_DEFINITIONS：唯一注册源，由 __init__.get_agent_tools 导出为 LangChain 工具
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import Field, field_validator, model_validator

from app.core.agent.tools.governance import (
    Effect,
    Risk,
    StrictArgs,
    ToolDefinition,
    ToolPolicy,
)
from app.core.agent.tools.permissions import (
    PERM_AFTER_SALE_READ,
    PERM_CS_ESCALATE,
    PERM_INVOICE_DOWNLOAD,
    PERM_INVOICE_READ,
    PERM_LOGISTICS_READ,
    PERM_ORDER_READ,
    PERM_REFUND_CREATE,
    PERM_REFUND_READ,
)
from app.core.config import get_settings
from app.service import after_sales as after_sale_service
from app.service import invoices as invoice_service
from app.service import logistics as logistics_service
from app.service import orders as order_service
from app.service import refunds as refund_service

# ---------------------------------------------------------------------------
# 标识约束（与 fake_data / 系统提示示例对齐，位数留余量，拒绝明显脏输入）
# 示例：O20261002002 / 2026100210000002 / SF1234567890 /
#       AS20260925001 / RF20260929001 / INV20260929001
# ---------------------------------------------------------------------------

ORDER_ID_PATTERN = r"^O\d{8,}$"  # 内部订单 ID
ORDER_NO_PATTERN = r"^\d{16}$"  # 对外订单号（16 位数字）
TRACKING_NO_PATTERN = r"^[A-Za-z0-9]{6,32}$"  # 运单号
AFTER_SALE_ID_PATTERN = r"^AS\d{8,}$"  # 售后单号
REFUND_ID_PATTERN = r"^RF\d{8,}$"  # 退款单号
INVOICE_ID_PATTERN = r"^INV\d{8,}$"  # 发票 ID

# ---------------------------------------------------------------------------
# 复用策略工厂：按业务域绑定 permission，供 PermissionEngine 校验
# ---------------------------------------------------------------------------


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
LOGISTICS_READ_POLICY = _read_policy(PERM_LOGISTICS_READ)
AFTER_SALE_READ_POLICY = _read_policy(PERM_AFTER_SALE_READ)
REFUND_READ_POLICY = _read_policy(PERM_REFUND_READ)
INVOICE_READ_POLICY = _read_policy(PERM_INVOICE_READ)
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
    # 当前无人工确认 UI：不强制 requires_confirmation，仅靠权限码控制
)
CREATE_REFUND_POLICY = ToolPolicy(
    effect=Effect.WRITE,
    risk=Risk.HIGH,
    permission=PERM_REFUND_CREATE,
    timeout_seconds=5.0,
    max_retries=0,
    # HITL：risk=HIGH + effect=WRITE → HumanInTheLoopMiddleware
    idempotent=True,
)


def _empty_to_none(value: Any) -> Any:
    """模型常传空字符串表示「未填」；转成 None 以跳过 pattern 校验。"""
    if isinstance(value, str) and not value.strip():
        return None
    return value


# ---------------------------------------------------------------------------
# 参数契约（StrictArgs：extra=forbid + 字段约束）
# ---------------------------------------------------------------------------


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
    """按订单号或订单 ID 二选一（进度查询、发票列表等依赖订单上下文的工具）。"""

    order_no: Optional[str] = Field(default=None, pattern=ORDER_NO_PATTERN)
    order_id: Optional[str] = Field(default=None, pattern=ORDER_ID_PATTERN)

    @field_validator("order_no", "order_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: Any) -> Any:
        return _empty_to_none(value)

    @model_validator(mode="after")
    def require_one_identifier(self) -> OrderLookupArgs:
        # 与 service 层「二选一必填」约定一致，尽早在参数门禁拒绝
        if not self.order_no and not self.order_id:
            raise ValueError("必须提供 order_no 或 order_id 之一")
        return self


class OptionalOrderLookupArgs(StrictArgs):
    """订单过滤可选（如退款列表：无过滤则返回当前数据集全集）。"""

    order_no: Optional[str] = Field(default=None, pattern=ORDER_NO_PATTERN)
    order_id: Optional[str] = Field(default=None, pattern=ORDER_ID_PATTERN)

    @field_validator("order_no", "order_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: Any) -> Any:
        return _empty_to_none(value)


class GetRefundDetailArgs(StrictArgs):
    """退款详情：退款单号必填。"""

    refund_id: str = Field(pattern=REFUND_ID_PATTERN)


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



# ---------------------------------------------------------------------------
# handlers：校验通过后的实际业务调用（同步，由 governance.invoke_tool 调度）
# ---------------------------------------------------------------------------


def _query_orders(args: QueryOrdersArgs) -> dict[str, Any]:
    raw = order_service.list_orders(
        order_no=args.order_no,
        order_id=args.order_id,
        status=args.status,
        keyword=args.keyword,
        page=args.page,
        page_size=args.page_size,
    )
    return _slim_order_list_for_agent(raw)


def _slim_order_list_for_agent(payload: dict[str, Any]) -> dict[str, Any]:
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


def _get_order_detail(args: GetOrderDetailArgs) -> dict[str, Any]:
    return order_service.get_order_detail(order_id=args.order_id)


def _get_order_by_no(args: GetOrderByNoArgs) -> dict[str, Any]:
    return order_service.get_order_detail(order_no=args.order_no)


def _get_logistics_by_order_no(args: GetLogisticsByOrderNoArgs) -> dict[str, Any]:
    return logistics_service.get_by_order_no(args.order_no, include_eta=args.include_eta)


def _get_logistics_tracking(args: GetLogisticsTrackingArgs) -> dict[str, Any]:
    return logistics_service.get_by_tracking(
        args.tracking_no,
        express_company_code=args.express_company_code,
        include_eta=args.include_eta,
    )


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


_EMAIL_KEY = re.compile(r"^(e[_-]?mail|mail)$", re.I)
_PUSHED_EMAIL_STEP = re.compile(r"发送邮箱|发邮件|邮件推送")


def _drop_email_keys(value: Any) -> Any:
    """递归删除 email/mail 键，避免送模。"""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _EMAIL_KEY.match(str(key)):
                continue
            out[str(key)] = _drop_email_keys(item)
        return out
    if isinstance(value, list):
        return [_drop_email_keys(item) for item in value]
    return value


def _party_for_agent(party: Any) -> dict[str, Any] | None:
    if not isinstance(party, dict):
        return None
    return {
        "name": party.get("name"),
        "taxNo": party.get("taxNo"),
    }


def slim_invoice_for_agent(payload: dict[str, Any]) -> dict[str, Any]:
    """发票详情送模视图：allowlist + 去掉邮件与「已发送邮箱」进度。"""
    if not isinstance(payload, dict):
        return payload
    if payload.get("error"):
        return _drop_email_keys(payload)

    title_in = payload.get("title") if isinstance(payload.get("title"), dict) else {}
    title = {
        "titleType": title_in.get("titleType"),
        "titleName": title_in.get("titleName"),
        "taxNo": title_in.get("taxNo"),
    }

    progress_in = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    steps_out: list[dict[str, Any]] = []
    for step in progress_in.get("steps") or []:
        if not isinstance(step, dict):
            continue
        code = str(step.get("step") or "").upper()
        text = str(step.get("stepText") or "")
        if code == "PUSHED" or _PUSHED_EMAIL_STEP.search(text):
            continue
        steps_out.append(
            {
                "step": step.get("step"),
                "stepText": step.get("stepText"),
                "status": step.get("status"),
                "time": step.get("time"),
            }
        )
    current = str(progress_in.get("currentStep") or "")
    if current.upper() == "PUSHED" or _PUSHED_EMAIL_STEP.search(current):
        current = str(steps_out[-1].get("step") or "ISSUED") if steps_out else ""

    slim: dict[str, Any] = {
        "invoiceId": payload.get("invoiceId"),
        "applicationNo": payload.get("applicationNo"),
        "orderId": payload.get("orderId"),
        "orderNo": payload.get("orderNo"),
        "status": payload.get("status"),
        "statusText": payload.get("statusText"),
        "invoiceType": payload.get("invoiceType"),
        "invoiceTypeText": payload.get("invoiceTypeText"),
        "amount": payload.get("amount"),
        "currency": payload.get("currency"),
        "title": title,
        "invoiceCode": payload.get("invoiceCode"),
        "invoiceNumber": payload.get("invoiceNumber"),
        "checkCode": payload.get("checkCode"),
        "issuedAt": payload.get("issuedAt"),
        "buyer": _party_for_agent(payload.get("buyer")),
        "seller": _party_for_agent(payload.get("seller")),
        "lineItems": payload.get("lineItems") or [],
        "files": payload.get("files") or [],
        "progress": {
            "currentStep": current,
            "steps": steps_out,
        },
        "failReason": payload.get("failReason"),
    }
    return _drop_email_keys(slim)


def _get_invoice(args: GetInvoiceArgs) -> dict[str, Any]:
    raw = invoice_service.get_invoice(args.invoice_id)
    if isinstance(raw, dict) and not raw.get("error"):
        return slim_invoice_for_agent(raw)
    return _drop_email_keys(raw) if isinstance(raw, dict) else raw


def _list_invoices_by_order(args: OrderLookupArgs) -> dict[str, Any]:
    return invoice_service.list_by_order(order_id=args.order_id, order_no=args.order_no)


def _create_invoice_download_urls(args: CreateInvoiceDownloadUrlsArgs) -> dict[str, Any]:
    type_list = [t.strip().upper() for t in (args.types or "PDF").split(",") if t.strip()]
    return invoice_service.create_download_urls(
        args.invoice_id,
        types=type_list or ["PDF"],
        expire_seconds=args.expire_seconds,
    )


def _escalate_to_human_cs(args: EscalateToHumanCsArgs) -> dict[str, Any]:
    # 返回结构需含 csUrl，供 loop._attach_forced_human_cs 解析 humanCs
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


# ---------------------------------------------------------------------------
# 工具注册表：name / description / 参数模型 / 策略 / handler 一一绑定
# type: ignore — Handler 类型为 Callable[[StrictArgs], ...]，具体 Args 子类在运行时安全
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[ToolDefinition] = [
    # ---- 订单（order:read）----
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
    # ---- 物流（logistics:read）----
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
    # ---- 售后（after_sale:read）----
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
    # ---- 退款（refund:read）----
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
    # ---- 发票（invoice:read / invoice:download）----
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
        parameters_model=OrderLookupArgs,
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
    # ---- 人工客服兜底（cs:escalate）----
    ToolDefinition(
        name="escalate_to_human_cs",
        description=(
            "无法回答或超出订单/物流/售后/退款/发票能力时，转人工客服兜底，返回人工客服链接。"
            "业务范围内信息不全时应先追问或调用查询类工具，不要用本工具。"
        ),
        parameters_model=EscalateToHumanCsArgs,
        policy=ESCALATE_POLICY,
        handler=_escalate_to_human_cs,  # type: ignore[arg-type]
    ),
]


def get_tool_definition(name: str) -> ToolDefinition | None:
    """按工具名查找注册定义；不存在返回 None。"""
    for item in TOOL_DEFINITIONS:
        if item.name == name:
            return item
    return None
