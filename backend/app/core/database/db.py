"""PostgreSQL connectivity (optional). Fake-data mode does not require a live DB.

A2A 任务库使用独立的异步引擎，不看 use_fake_data。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings

_engine: Optional[Engine] = None
_async_engine: AsyncEngine | None = None


def get_engine() -> Optional[Engine]:
    global _engine
    settings = get_settings()
    if settings.use_fake_data:
        return None
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine


def _async_database_url(url: str) -> str:
    """异步引擎用 asyncpg。Windows 上 uvicorn 的 ProactorEventLoop 不能跑 psycopg 异步连接。"""
    if url.startswith("postgresql+psycopg://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql+psycopg://")
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    return url


def get_async_engine() -> AsyncEngine:
    """A2A DatabaseTaskStore 用的异步引擎。创建时不连库。"""
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            _async_database_url(get_settings().database_url),
            pool_pre_ping=True,
            connect_args={"timeout": 3},
        )
    return _async_engine


async def dispose_async_engine() -> None:
    global _async_engine
    engine = _async_engine
    _async_engine = None
    if engine is not None:
        await engine.dispose()


def ping_db() -> bool:
    engine = get_engine()
    if engine is None:
        return False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
