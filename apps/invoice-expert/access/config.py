"""发票专家：权限码、白名单、角色元数据。"""

from __future__ import annotations

from app.core.agent.tools.report import SUBMIT_REPORT

ROLE = "invoice"
PROMPT_KEY = "invoice_expert_system"
EXPERT_NAME = "invoice"
DEFAULT_AGENT_ID = "invoice-expert"
DEFAULT_AGENT_NAME = "发票专家"

PERM_INVOICE_READ = "invoice:read"
PERM_INVOICE_DOWNLOAD = "invoice:download"
PERM_CS_ESCALATE = "cs:escalate"

ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "get_invoice",
        "list_invoices_by_order",
        "create_invoice_download_urls",
        "escalate_to_human_cs",
        SUBMIT_REPORT,
    }
)

PERMISSIONS: frozenset[str] = frozenset(
    {
        PERM_INVOICE_READ,
        PERM_INVOICE_DOWNLOAD,
        PERM_CS_ESCALATE,
    }
)


def register_invoice_access() -> None:
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
