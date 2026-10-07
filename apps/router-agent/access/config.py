"""路由 Agent：权限码、白名单、角色元数据。"""

from __future__ import annotations

ROLE = "router"
PROMPT_KEY = "router_system"
DEFAULT_AGENT_ID = "router-agent"
DEFAULT_AGENT_NAME = "路由智能助手"

DISPATCH_ORDER = "dispatch_order_expert"
DISPATCH_LOGISTICS = "dispatch_logistics_expert"
DISPATCH_INVOICE = "dispatch_invoice_expert"

PERM_CS_ESCALATE = "cs:escalate"

ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        DISPATCH_ORDER,
        DISPATCH_LOGISTICS,
        DISPATCH_INVOICE,
        "escalate_to_human_cs",
    }
)

PERMISSIONS: frozenset[str] = frozenset({PERM_CS_ESCALATE})


def register_router_access() -> None:
    from app.core.agent.profiles import install_process_profile

    install_process_profile(
        role=ROLE,
        prompt_key=PROMPT_KEY,
        expert_name=None,
        agent_id=DEFAULT_AGENT_ID,
        agent_name=DEFAULT_AGENT_NAME,
        tools=ALLOWED_TOOLS,
        permissions=PERMISSIONS,
    )
