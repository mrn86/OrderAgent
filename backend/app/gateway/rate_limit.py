"""网关 HTTP 入口限流（按 Bearer token，滑动窗口）。"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque, Optional

from fastapi import Depends, Header, HTTPException, Request, status

from app.api.deps import require_auth
from app.core.audit import emit_gateway_audit, ensure_audit_request_id
from app.core.config import get_settings

_lock = Lock()
_hits: dict[str, Deque[float]] = defaultdict(deque)


def _prune(window: Deque[float], now: float, window_seconds: float) -> None:
    while window and now - window[0] > window_seconds:
        window.popleft()


def check_rate_limit(
    request: Request,
    token: str = Depends(require_auth),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
) -> str:
    """Agent 路由依赖：超过 GATEWAY_RATE_LIMIT_PER_MINUTE 则 429。"""
    ensure_audit_request_id(x_request_id=x_request_id)
    settings = get_settings()
    limit = max(1, int(settings.gateway_rate_limit_per_minute))
    window_seconds = 60.0
    key = token or "anonymous"
    now = time.monotonic()

    from app.core.redis_client import get_redis

    client = get_redis(for_stream=True)
    if client is not None:
        rkey = f"oa:rl:{key}"
        count = int(client.incr(rkey))
        if count == 1:
            client.expire(rkey, int(window_seconds))
        if count > limit:
            ttl = int(client.ttl(rkey) or window_seconds)
            retry_after = max(1, ttl)
            emit_gateway_audit(
                path=request.url.path,
                method=request.method,
                auth_ok=True,
                token=token,
                gateway_rate_limited=True,
                retry_after=retry_after,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                model_fallback=None,
                model_rate_limited=None,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁，每分钟最多 {limit} 次",
                headers={"Retry-After": str(retry_after)},
            )
        return token

    with _lock:
        bucket = _hits[key]
        _prune(bucket, now, window_seconds)
        if len(bucket) >= limit:
            oldest = bucket[0]
            retry_after = max(1, int(window_seconds - (now - oldest)) + 1)
            emit_gateway_audit(
                path=request.url.path,
                method=request.method,
                auth_ok=True,
                token=token,
                gateway_rate_limited=True,
                retry_after=retry_after,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                model_fallback=None,
                model_rate_limited=None,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁，每分钟最多 {limit} 次",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)
    return token
