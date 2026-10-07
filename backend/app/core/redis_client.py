"""Redis connectivity (optional). Used for cache + SSE streams when available."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client = None
_async_client = None
_memory_cache: dict[str, str] = {}


def get_redis(*, for_stream: bool = False):
    """同步客户端。

    for_stream=True 时不因 use_fake_data 禁用（任务总线 / SSE 依赖 Stream）。
    """
    global _client
    settings = get_settings()
    if settings.use_fake_data and not for_stream:
        return None
    if _client is None:
        try:
            import redis

            _client = redis.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                protocol=2,
            )
            _client.ping()
        except Exception:
            _client = False
    return _client if _client is not False else None


async def get_async_redis(*, for_stream: bool = False):
    """异步客户端。

    for_stream=True 时不因 use_fake_data 禁用（SSE 跨实例依赖 Redis Stream）。
    连接失败返回 None。
    """
    global _async_client
    settings = get_settings()
    if settings.use_fake_data and not for_stream:
        return None
    if _async_client is False:
        return None
    if _async_client is not None:
        return _async_client
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            protocol=2,  # 兼容不支持 HELLO/RESP3 的旧版 Redis
        )
        await client.ping()
        _async_client = client
        return _async_client
    except Exception:
        logger.warning("async Redis 连接失败", exc_info=True)
        _async_client = False
        return None


def cache_get(key: str) -> Optional[Any]:
    client = get_redis()
    if client is None:
        raw = _memory_cache.get(key)
    else:
        raw = client.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return raw


def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> None:
    raw = json.dumps(value, ensure_ascii=False)
    client = get_redis()
    if client is None:
        _memory_cache[key] = raw
        return
    client.setex(key, ttl_seconds, raw)


def ping_redis() -> bool:
    client = get_redis()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except Exception:
        return False
