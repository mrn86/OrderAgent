"""系统提示词存储：PostgreSQL + 内存兜底。默认内容由各 Agent 进程安装。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class SystemPrompt(Base):
    __tablename__ = "system_prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prompt_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


@dataclass(frozen=True)
class PromptRecord:
    prompt_key: str
    content: str
    version: str
    enabled: bool


_prompt_engine = None
_SessionLocal: Optional[sessionmaker] = None
_schema_ready = False
_prompt_engine_failed = False

# 本进程安装的默认提示词：(prompt_key, version, content)
_PROCESS_DEFAULTS: list[tuple[str, str, str]] = []

# PG 不可用时的内存表（仍按「每次查询」路径走，不缓存业务结果）
_memory_rows: list[dict] = []


def install_process_prompts(defaults: list[tuple[str, str, str]]) -> None:
    """本进程只种子这些提示词，不共享其他 Agent 的默认内容。"""
    global _PROCESS_DEFAULTS, _schema_ready, _memory_rows
    _PROCESS_DEFAULTS = list(defaults)
    _schema_ready = False
    _memory_rows = []


def _defaults() -> list[tuple[str, str, str]]:
    return list(_PROCESS_DEFAULTS)


def get_prompt_engine():
    """提示词专用引擎：不依赖 USE_FAKE_DATA（业务假数据可与提示词库并存）。"""
    global _prompt_engine, _SessionLocal, _prompt_engine_failed
    if _prompt_engine is not None:
        return _prompt_engine
    if _prompt_engine_failed:
        return None
    settings = get_settings()
    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        _prompt_engine = engine
        _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        return _prompt_engine
    except Exception as exc:  # noqa: BLE001
        _prompt_engine_failed = True
        logger.warning("提示词库 PostgreSQL 不可用，将使用内存兜底: %s", exc)
        _prompt_engine = None
        _SessionLocal = None
        return None


def _seed_memory() -> None:
    global _memory_rows
    if _memory_rows:
        return
    now = datetime.now(timezone.utc)
    _memory_rows = [
        {
            "id": i + 1,
            "prompt_key": key,
            "content": content,
            "version": version,
            "enabled": True,
            "created_at": now,
            "updated_at": now,
        }
        for i, (key, version, content) in enumerate(_defaults())
    ]


def ensure_prompt_schema() -> None:
    """建表并写入本进程已安装的默认版本。"""
    global _schema_ready
    engine = get_prompt_engine()
    if engine is None:
        _seed_memory()
        _schema_ready = True
        return

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_system_prompts_key_version
                ON system_prompts (prompt_key, version)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_system_prompts_one_enabled
                ON system_prompts (prompt_key)
                WHERE enabled = TRUE
                """
            )
        )

    assert _SessionLocal is not None
    with _SessionLocal() as session:
        for key, version, content in _defaults():
            exists_version = session.scalar(
                select(SystemPrompt.id).where(
                    SystemPrompt.prompt_key == key,
                    SystemPrompt.version == version,
                )
            )
            if exists_version:
                continue
            for row in session.scalars(
                select(SystemPrompt).where(
                    SystemPrompt.prompt_key == key,
                    SystemPrompt.enabled.is_(True),
                )
            ):
                row.enabled = False
            session.add(
                SystemPrompt(
                    prompt_key=key,
                    content=content,
                    version=version,
                    enabled=True,
                )
            )
        session.commit()
    _schema_ready = True
    logger.info("system_prompts 表已就绪 defaults=%s", [k for k, _, _ in _defaults()])


def _ensure_ready() -> None:
    if not _schema_ready:
        ensure_prompt_schema()


def get_enabled_prompt(prompt_key: str) -> PromptRecord:
    """每次调用都查询当前启用的提示词（不读进程内业务缓存）。"""
    _ensure_ready()
    engine = get_prompt_engine()
    if engine is None or _SessionLocal is None:
        _seed_memory()
        for row in _memory_rows:
            if row["prompt_key"] == prompt_key and row["enabled"]:
                return PromptRecord(
                    prompt_key=row["prompt_key"],
                    content=row["content"],
                    version=row["version"],
                    enabled=True,
                )
        for key, version, content in _defaults():
            if key == prompt_key:
                return PromptRecord(prompt_key=key, content=content, version=version, enabled=True)
        raise RuntimeError(f"未找到提示词: {prompt_key}")

    with _SessionLocal() as session:
        row = session.scalar(
            select(SystemPrompt)
            .where(
                SystemPrompt.prompt_key == prompt_key,
                SystemPrompt.enabled.is_(True),
            )
            .limit(1)
        )
        if row is None:
            raise RuntimeError(f"数据库中无启用的提示词: {prompt_key}")
        return PromptRecord(
            prompt_key=row.prompt_key,
            content=row.content,
            version=row.version,
            enabled=row.enabled,
        )
