"""物流专家：权限码、白名单、角色元数据。"""

from __future__ import annotations

from app.core.agent.tools.report import SUBMIT_REPORT

ROLE = "logistics"
PROMPT_KEY = "logistics_expert_system"
EXPERT_NAME = "logistics"
DEFAULT_AGENT_ID = "logistics-expert"
DEFAULT_AGENT_NAME = "Logistics Expert"

PERM_LOGISTICS_READ = "logistics:read"
PERM_ORDER_READ = "order:read"
PERM_CS_ESCALATE = "cs:escalate"

ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "get_logistics_by_order_no",
        "get_logistics_tracking",
        "get_order_by_no",
        "get_order_detail",
        "escalate_to_human_cs",
        SUBMIT_REPORT,
    }
)

PERMISSIONS: frozenset[str] = frozenset(
    {
        PERM_LOGISTICS_READ,
        PERM_ORDER_READ,
        PERM_CS_ESCALATE,
    }
)


def register_logistics_access() -> None:
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
