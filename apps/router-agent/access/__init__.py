"""路由 Agent 白名单与权限。"""

from access.config import (
    ALLOWED_TOOLS,
    DISPATCH_INVOICE,
    DISPATCH_LOGISTICS,
    DISPATCH_ORDER,
    PERMISSIONS,
    PERM_CS_ESCALATE,
    register_router_access,
)

__all__ = [
    "ALLOWED_TOOLS",
    "DISPATCH_INVOICE",
    "DISPATCH_LOGISTICS",
    "DISPATCH_ORDER",
    "PERMISSIONS",
    "PERM_CS_ESCALATE",
    "register_router_access",
]
