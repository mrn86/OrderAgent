"""订单专家白名单与权限。"""

from access.config import (
    ALLOWED_TOOLS,
    PERMISSIONS,
    PERM_AFTER_SALE_READ,
    PERM_CS_ESCALATE,
    PERM_ORDER_READ,
    PERM_REFUND_CREATE,
    PERM_REFUND_READ,
    register_order_access,
)

__all__ = [
    "ALLOWED_TOOLS",
    "PERMISSIONS",
    "PERM_AFTER_SALE_READ",
    "PERM_CS_ESCALATE",
    "PERM_ORDER_READ",
    "PERM_REFUND_CREATE",
    "PERM_REFUND_READ",
    "register_order_access",
]
