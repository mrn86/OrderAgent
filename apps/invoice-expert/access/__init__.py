"""发票专家白名单与权限。"""

from access.config import (
    ALLOWED_TOOLS,
    PERMISSIONS,
    PERM_CS_ESCALATE,
    PERM_INVOICE_DOWNLOAD,
    PERM_INVOICE_READ,
    register_invoice_access,
)

__all__ = [
    "ALLOWED_TOOLS",
    "PERMISSIONS",
    "PERM_CS_ESCALATE",
    "PERM_INVOICE_DOWNLOAD",
    "PERM_INVOICE_READ",
    "register_invoice_access",
]
