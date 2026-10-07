"""系统提示词模板：PostgreSQL 存储，每次 LLM 调用实时查询启用版本。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)

PROMPT_KEY_AGENT_SYSTEM = "agent_system"
PROMPT_KEY_ROUTER = "router_system"
PROMPT_KEY_ORDER = "order_expert_system"
PROMPT_KEY_LOGISTICS = "logistics_expert_system"
PROMPT_KEY_INVOICE = "invoice_expert_system"

_ANTI_FABRICATE = """
禁止编造（硬规则）：
- 只陈述工具/复核实际返回的事实；无成功工具结果不得编造字段、状态、金额、链接或动作。
- 不得声称系统未实现的能力（发邮件、发短信、推送通知等）。
- 证据不足时追问或转人工，禁止猜测补全。
"""

DEFAULT_AGENT_SYSTEM = """你是订单智能助手，只处理：订单、物流、售后、退款、发票。
可调用工具查询真实数据，并可发起仅退款。选哪个工具、传什么参数，一律以当前可用工具的描述与参数说明为准，不要依赖本提示中的接口名。
""" + _ANTI_FABRICATE + """
输出：
- 全程中文；标识（订单号/运单号/ID）可保留原文。
- 禁止英文旁白或计划语；需要过渡只用中文短句，或直接调工具。
- 先结论后细节，简洁。
- 最终答复必须使用 Markdown（不要用 HTML、不要用 ``` 代码块包住整段）。结论一行加粗；字段用 `- 标签：值` 列表；流程用有序列表；对比用表格；链接用 [文案](url)。
  示例：
  **物流状态：运输中**
  - 订单号：`2026100210000002`
  - 运单号：`SF1234567890`

工具：
- 优先调工具，禁止编造订单/物流/退款/发票结果。
- 金额对外说「元」；写入工具的金额字段遵循该工具自己的单位说明。
- 用户已给发票 ID（INV…）：直接查详情/下载链接，不要用发票 ID 当订单号去查发票列表；禁止声称已发送邮箱。
- 「查看全部订单/我的订单」：列表工具成功一次后立即作答，不要逐笔再查详情。
- 同一工具、相同参数已经成功返回后禁止再调。

多轮与指代：
- 「需要/好的/可以/继续」等短回复，按上一轮助手提议继续执行。
- 「第N笔/第二笔/上一笔/那笔订单」：先查订单列表（或用历史列表）按序号定位，再查详情/物流/退款；不要因缺订单号就转人工。

人工客服：
- 仅当：①问题明显超出上述能力；或②已调相关工具仍无法继续。
- 意图不清时：先用一句话澄清；澄清后仍无法归入上述能力再转人工。
- 业务范围内信息不全：只追问或先调工具，禁止转人工。
转人工时须说明原因，并引导用户点击工具返回的客服链接（勿编造链接）。

示例数据：订单号 2026100210000002（运输中，售后退货 AS20260925001），
订单号 2026091508765432（已完成，仅退款 RF20260929001 / AS20260918008），
运单 SF1234567890，发票 INV20260929001。
"""


DEFAULT_ROUTER_SYSTEM = """你是客服路由助手，只负责理解用户意图并指派专家，不直接查询订单、物流或发票明细。
可调用工具：
- dispatch_order_expert：订单、售后、退款（不含物流轨迹）
- dispatch_logistics_expert：物流轨迹、运单、时效预测
- dispatch_invoice_expert：发票详情/列表/下载
- escalate_to_human_cs：超出范围再转人工
""" + _ANTI_FABRICATE + """
规则：
- 全程中文。最终答复用 Markdown，结论加粗。
- 指派时必须填写 reason（为何派给该专家）和 instruction（用户问题+已知单号/运单号，不要把另一专家结论当事实）。
- 跨域问题可分别派发订单、物流、发票专家，由你合并答复；合并时只使用工具返回的 conclusion / risks / unresolved 等业务事实。
- 用户说「查看全部订单/我的订单/订单列表」：dispatch_order_expert 的 instruction 写明「无需订单号，直接 query_orders 拉列表并汇总」；收到 conclusion 后直接展示列表，禁止向用户索要订单号、手机号或账号。
- 必须阅读返回的 verified.issues；有冲突或证据不足时用更明确 instruction 再派同一专家（supplement/由工具自动复核）。
- status=need_hitl 时停止调用工具，把审批信息交给用户。
- 禁止向用户声称已发邮件/短信或任何未由工具确认的动作。
- 最终对用户答复必须是可读的业务说明（订单状态、金额、物流、发票等），禁止粘贴或复述 JSON、report、verified、taskId、evidence、commands、result_hash 或任何工具原始字段。
"""

DEFAULT_ORDER_EXPERT = """你是订单专家，只处理订单、售后、退款。不处理物流轨迹与运单查询。
必须调用业务工具查真实数据，结束前必须调用 submit_expert_report 提交结构化报告。
报告含：conclusion、evidence（source/id/excerpt/result_hash）、path、commands、risks、confidence、unresolved、suggested_next、status。
""" + _ANTI_FABRICATE + """
全程中文；标识可保留原文。金额对用户说「元」，写入工具按该工具单位。
「查看全部订单/我的订单/订单列表」：必须直接调用 query_orders（可不传订单号），用返回 list 写 conclusion（订单号、状态、实付、商品摘要），status=done、confidence≥0.8；
禁止因此追问订单号/手机号/账号，禁止对每笔再调详情除非用户点名某一笔。
同一工具相同参数成功后不要重复调用。无法处理时 escalate_to_human_cs。
"""

DEFAULT_LOGISTICS_EXPERT = """你是物流专家，只处理物流轨迹、运单号和时效预测。
用户给订单号时用 get_logistics_by_order_no；给运单号时用 get_logistics_tracking。
可用 get_order_by_no / get_order_detail 核对订单号，不要处理退款、售后或发票。
结束前必须 submit_expert_report。
""" + _ANTI_FABRICATE + """
全程中文。轨迹与时效只能来自物流工具返回。
"""

DEFAULT_INVOICE_EXPERT = """你是发票专家，只处理发票查询与下载。
用户给 INV 开头发票 ID 时直接 get_invoice / create_invoice_download_urls，不要把发票 ID 当订单号。
仅有订单号时用 list_invoices_by_order。可用 get_order_by_no 核对订单号，不要处理退款/物流。
用户要文件时调用 create_invoice_download_urls 给出下载链接；禁止声称已发送邮箱/短信。
结束前必须 submit_expert_report。
""" + _ANTI_FABRICATE + """
全程中文。抬头、金额、状态、下载链接必须来自工具结果。
"""


class Base(DeclarativeBase):
    pass


class SystemPrompt(Base):
    __tablename__ = "system_prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prompt_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


@dataclass(frozen=True)
class PromptRecord:
    prompt_key: str
    content: str
    version: str
    enabled: bool


_prompt_engine = None
_SessionLocal: Optional[sessionmaker] = None
_schema_ready = False
_prompt_engine_failed = False

# PG 不可用时的内存表（仍按「每次查询」路径走，不缓存业务结果）
_memory_rows: list[dict] = []


def _defaults() -> list[tuple[str, str, str]]:
    return [
        (PROMPT_KEY_AGENT_SYSTEM, "1.3.9", DEFAULT_AGENT_SYSTEM),
        (PROMPT_KEY_ROUTER, "1.2.2", DEFAULT_ROUTER_SYSTEM),
        (PROMPT_KEY_ORDER, "1.2.1", DEFAULT_ORDER_EXPERT),
        (PROMPT_KEY_LOGISTICS, "1.1.0", DEFAULT_LOGISTICS_EXPERT),
        (PROMPT_KEY_INVOICE, "1.1.0", DEFAULT_INVOICE_EXPERT),
    ]


def get_prompt_engine():
    """提示词专用引擎：不依赖 USE_FAKE_DATA（业务假数据可与提示词库并存）。"""
    global _prompt_engine, _SessionLocal, _prompt_engine_failed
    if _prompt_engine is not None:
        return _prompt_engine
    if _prompt_engine_failed:
        return None
    settings = get_settings()
    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        _prompt_engine = engine
        _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        return _prompt_engine
    except Exception as exc:  # noqa: BLE001
        _prompt_engine_failed = True
        logger.warning("提示词库 PostgreSQL 不可用，将使用内存兜底: %s", exc)
        _prompt_engine = None
        _SessionLocal = None
        return None


def _seed_memory() -> None:
    global _memory_rows
    if _memory_rows:
        return
    now = datetime.now(timezone.utc)
    _memory_rows = [
        {
            "id": i + 1,
            "prompt_key": key,
            "content": content,
            "version": version,
            "enabled": True,
            "created_at": now,
            "updated_at": now,
        }
        for i, (key, version, content) in enumerate(_defaults())
    ]


def ensure_prompt_schema() -> None:
    """建表并写入默认启用版本（仅当该 key 尚无任何记录时）。"""
    global _schema_ready
    engine = get_prompt_engine()
    if engine is None:
        _seed_memory()
        _schema_ready = True
        return

    Base.metadata.create_all(engine)
    # 部分唯一：同一 prompt_key 仅允许一条 enabled=true
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_system_prompts_key_version
                ON system_prompts (prompt_key, version)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_system_prompts_one_enabled
                ON system_prompts (prompt_key)
                WHERE enabled = TRUE
                """
            )
        )

    assert _SessionLocal is not None
    with _SessionLocal() as session:
        for key, version, content in _defaults():
            exists_version = session.scalar(
                select(SystemPrompt.id).where(
                    SystemPrompt.prompt_key == key,
                    SystemPrompt.version == version,
                )
            )
            if exists_version:
                continue
            # 新版本：关闭同 key 旧启用行，再写入并启用本版
            for row in session.scalars(
                select(SystemPrompt).where(
                    SystemPrompt.prompt_key == key,
                    SystemPrompt.enabled.is_(True),
                )
            ):
                row.enabled = False
            session.add(
                SystemPrompt(
                    prompt_key=key,
                    content=content,
                    version=version,
                    enabled=True,
                )
            )
        session.commit()
    _schema_ready = True
    logger.info("system_prompts 表已就绪")


def _ensure_ready() -> None:
    if not _schema_ready:
        ensure_prompt_schema()


def get_enabled_prompt(prompt_key: str) -> PromptRecord:
    """每次调用都查询当前启用的提示词（不读进程内业务缓存）。"""
    _ensure_ready()
    engine = get_prompt_engine()
    if engine is None or _SessionLocal is None:
        _seed_memory()
        for row in _memory_rows:
            if row["prompt_key"] == prompt_key and row["enabled"]:
                return PromptRecord(
                    prompt_key=row["prompt_key"],
                    content=row["content"],
                    version=row["version"],
                    enabled=True,
                )
        # 极端兜底
        for key, version, content in _defaults():
            if key == prompt_key:
                return PromptRecord(prompt_key=key, content=content, version=version, enabled=True)
        raise RuntimeError(f"未找到提示词: {prompt_key}")

    with _SessionLocal() as session:
        row = session.scalar(
            select(SystemPrompt)
            .where(
                SystemPrompt.prompt_key == prompt_key,
                SystemPrompt.enabled.is_(True),
            )
            .limit(1)
        )
        if row is None:
            raise RuntimeError(f"数据库中无启用的提示词: {prompt_key}")
        return PromptRecord(
            prompt_key=row.prompt_key,
            content=row.content,
            version=row.version,
            enabled=row.enabled,
        )


def get_enabled_prompt_content(prompt_key: str) -> str:
    return get_enabled_prompt(prompt_key).content
