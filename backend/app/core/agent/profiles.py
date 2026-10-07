"""四角色：路由 / 订单专家 / 物流专家 / 发票专家。工具白名单与 thread_id 隔离。"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.agent.tools.permissions import (
    ALL_AGENT_PERMISSIONS,
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

ROLE_ROUTER = "router"
ROLE_ORDER = "order"
ROLE_LOGISTICS = "logistics"
ROLE_INVOICE = "invoice"

PROMPT_KEY_ROUTER = "router_system"
PROMPT_KEY_ORDER = "order_expert_system"
PROMPT_KEY_LOGISTICS = "logistics_expert_system"
PROMPT_KEY_INVOICE = "invoice_expert_system"

DISPATCH_ORDER = "dispatch_order_expert"
DISPATCH_LOGISTICS = "dispatch_logistics_expert"
DISPATCH_INVOICE = "dispatch_invoice_expert"
SUBMIT_REPORT = "submit_expert_report"

ORDER_TOOLS: frozenset[str] = frozenset(
    {
        "query_orders",
        "get_order_detail",
        "get_order_by_no",
        "list_after_sales",
        "get_after_sale_detail",
        "get_after_sale_progress",
        "list_refunds",
        "get_refund_detail",
        "get_refund_progress",
        "create_refund",
        "escalate_to_human_cs",
        SUBMIT_REPORT,
    }
)

LOGISTICS_TOOLS: frozenset[str] = frozenset(
    {
        "get_logistics_by_order_no",
        "get_logistics_tracking",
        "get_order_by_no",
        "get_order_detail",
        "escalate_to_human_cs",
        SUBMIT_REPORT,
    }
)

INVOICE_TOOLS: frozenset[str] = frozenset(
    {
        "get_invoice",
        "list_invoices_by_order",
        "create_invoice_download_urls",
        "get_order_by_no",
        "get_order_detail",
        "escalate_to_human_cs",
        SUBMIT_REPORT,
    }
)

ROUTER_TOOLS: frozenset[str] = frozenset(
    {
        DISPATCH_ORDER,
        DISPATCH_LOGISTICS,
        DISPATCH_INVOICE,
        "escalate_to_human_cs",
    }
)

ORDER_PERMISSIONS: frozenset[str] = frozenset(
    {
        PERM_ORDER_READ,
        PERM_AFTER_SALE_READ,
        PERM_REFUND_READ,
        PERM_REFUND_CREATE,
        PERM_CS_ESCALATE,
    }
)

LOGISTICS_PERMISSIONS: frozenset[str] = frozenset(
    {
        PERM_LOGISTICS_READ,
        PERM_ORDER_READ,
        PERM_CS_ESCALATE,
    }
)

INVOICE_PERMISSIONS: frozenset[str] = frozenset(
    {
        PERM_INVOICE_READ,
        PERM_INVOICE_DOWNLOAD,
        PERM_ORDER_READ,
        PERM_CS_ESCALATE,
    }
)

ROUTER_PERMISSIONS: frozenset[str] = frozenset({PERM_CS_ESCALATE})


@dataclass(frozen=True)
class AgentProfile:
    role: str
    agent_id: str
    agent_name: str
    prompt_key: str
    tools: frozenset[str]
    permissions: frozenset[str]
    expert_name: str | None  # dispatch 目标：order / logistics / invoice


def expert_thread_id(conversation_id: str, agent_id: str, task_id: str) -> str:
    return f"{conversation_id}:{agent_id}:{task_id}"


def profile_for_role(role: str | None = None) -> AgentProfile:
    settings = get_settings()
    resolved = (role or settings.agent_role or ROLE_ROUTER).strip().lower()
    if resolved in {"order", "order-expert", "order_expert"}:
        return AgentProfile(
            role=ROLE_ORDER,
            agent_id=settings.agent_id or "order-expert",
            agent_name=settings.agent_name or "Order Expert",
            prompt_key=PROMPT_KEY_ORDER,
            tools=ORDER_TOOLS,
            permissions=ORDER_PERMISSIONS,
            expert_name=ROLE_ORDER,
        )
    if resolved in {"logistics", "logistics-expert", "logistics_expert"}:
        return AgentProfile(
            role=ROLE_LOGISTICS,
            agent_id=settings.agent_id or "logistics-expert",
            agent_name=settings.agent_name or "Logistics Expert",
            prompt_key=PROMPT_KEY_LOGISTICS,
            tools=LOGISTICS_TOOLS,
            permissions=LOGISTICS_PERMISSIONS,
            expert_name=ROLE_LOGISTICS,
        )
    if resolved in {"invoice", "invoice-expert", "invoice_expert"}:
        return AgentProfile(
            role=ROLE_INVOICE,
            agent_id=settings.agent_id or "invoice-expert",
            agent_name=settings.agent_name or "Invoice Expert",
            prompt_key=PROMPT_KEY_INVOICE,
            tools=INVOICE_TOOLS,
            permissions=INVOICE_PERMISSIONS,
            expert_name=ROLE_INVOICE,
        )
    return AgentProfile(
        role=ROLE_ROUTER,
        agent_id=settings.agent_id or "router-agent",
        agent_name=settings.agent_name or "Router Agent",
        prompt_key=PROMPT_KEY_ROUTER,
        tools=ROUTER_TOOLS,
        permissions=ROUTER_PERMISSIONS | ALL_AGENT_PERMISSIONS,
        expert_name=None,
    )


def current_profile() -> AgentProfile:
    return profile_for_role()
