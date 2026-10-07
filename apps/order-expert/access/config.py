"""订单专家：权限码、白名单、角色元数据。"""

from __future__ import annotations

from app.core.agent.tools.report import SUBMIT_REPORT

ROLE = "order"
PROMPT_KEY = "order_expert_system"
EXPERT_NAME = "order"
DEFAULT_AGENT_ID = "order-expert"
DEFAULT_AGENT_NAME = "订单专家"

PERM_ORDER_READ = "order:read"
PERM_AFTER_SALE_READ = "after_sale:read"
PERM_REFUND_READ = "refund:read"
PERM_REFUND_CREATE = "refund:create"
PERM_CS_ESCALATE = "cs:escalate"

ALLOWED_TOOLS: frozenset[str] = frozenset(
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

PERMISSIONS: frozenset[str] = frozenset(
    {
        PERM_ORDER_READ,
        PERM_AFTER_SALE_READ,
        PERM_REFUND_READ,
        PERM_REFUND_CREATE,
        PERM_CS_ESCALATE,
    }
)


def register_order_access() -> None:
    from app.core.agent.profiles import install_process_profile

    install_process_profile(
        role=ROLE,
        prompt_key=PROMPT_KEY,
        expert_name=EXPERT_NAME,
        agent_id=DEFAULT_AGENT_ID,
        agent_name=DEFAULT_AGENT_NAME,
        tools=ALLOWED_TOOLS,
        permissions=PERMISSIONS,
    )
