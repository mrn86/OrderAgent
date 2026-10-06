from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, Request, status

from app.core.audit import emit_gateway_audit, ensure_audit_request_id
from app.core.config import get_settings


def require_auth(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
) -> str:
    ensure_audit_request_id(x_request_id=x_request_id)
    settings = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        emit_gateway_audit(
            path=request.url.path,
            method=request.method,
            auth_ok=False,
            status_code=status.HTTP_401_UNAUTHORIZED,
            model_fallback=None,
            model_rate_limited=None,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未认证")
    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.access_token:
        emit_gateway_audit(
            path=request.url.path,
            method=request.method,
            auth_ok=False,
            status_code=status.HTTP_401_UNAUTHORIZED,
            model_fallback=None,
            model_rate_limited=None,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 无效")
    return token
