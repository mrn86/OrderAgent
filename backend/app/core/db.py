"""PostgreSQL connectivity (optional). Fake-data mode does not require a live DB."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import get_settings

_engine: Optional[Engine] = None


def get_engine() -> Optional[Engine]:
    global _engine
    settings = get_settings()
    if settings.use_fake_data:
        return None
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine


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
