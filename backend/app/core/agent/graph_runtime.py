"""LangGraph 运行时：共享 checkpointer、HITL interrupt 读取与 runtime ContextVar。

thread_id = conversationId。对话历史由 checkpointer 跨轮次、跨进程恢复。

流式 astream 走 checkpointer 的异步接口；同步 PostgresSaver 本身未实现
aget_tuple/aput，这里用 to_thread 包装，避免 NotImplementedError。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from contextvars import ContextVar, Token
from typing import Any, NotRequired

from langchain.agents import AgentState
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_checkpointer: BaseCheckpointSaver | None = None
_graph_var: ContextVar[Any] = ContextVar("order_agent_graph")
_thread_var: ContextVar[str] = ContextVar("order_agent_thread")


class OrderAgentState(AgentState):
    """默认 messages + 压缩用短时记忆槽。"""

    working_memory: NotRequired[dict[str, Any]]


class AsyncCompatPostgresSaver(PostgresSaver):
    """为同步 PostgresSaver 补齐 astream 所需的异步方法。"""

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return await asyncio.to_thread(self.get_tuple, config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        items = await asyncio.to_thread(
            lambda: list(self.list(config, filter=filter, before=before, limit=limit))
        )
        for item in items:
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        await asyncio.to_thread(self.delete_thread, thread_id)


def _to_psycopg_conninfo(database_url: str) -> str:
    """SQLAlchemy URL → psycopg 连接串。"""
    url = (database_url or "").strip()
    for prefix in (
        "postgresql+psycopg://",
        "postgresql+psycopg2://",
        "postgres+psycopg://",
    ):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    return url


def _build_postgres_checkpointer() -> AsyncCompatPostgresSaver:
    global _pool
    conninfo = _to_psycopg_conninfo(get_settings().database_url)
    _pool = ConnectionPool(
        conninfo=conninfo,
        max_size=10,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    saver = AsyncCompatPostgresSaver(_pool)
    saver.setup()
    return saver


def get_checkpointer() -> BaseCheckpointSaver:
    """懒加载：优先 Postgres；库不可用时回退 MemorySaver。"""
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    try:
        _checkpointer = _build_postgres_checkpointer()
        logger.info("LangGraph checkpointer: PostgreSQL")
    except Exception:
        logger.exception("PostgreSQL checkpointer 初始化失败，回退 MemorySaver")
        _checkpointer = MemorySaver()
    return _checkpointer


def ensure_checkpointer() -> BaseCheckpointSaver:
    """应用启动时预热：建表 / 打开连接池。"""
    return get_checkpointer()


def thread_config(conversation_id: str) -> dict[str, Any]:
    """只带 thread_id。不要在这里写 recursion_limit：

    等于默认 25 的值在 merge_configs 里会被忽略；写成 80 又会覆盖
    create_agent 绑定的 9999。中间件节点过多时，25 会在正常工具轮次上先炸。
    """
    return {"configurable": {"thread_id": conversation_id}}


def bind_runtime(graph: Any, conversation_id: str) -> tuple[Token[Any], Token[str]]:
    return _graph_var.set(graph), _thread_var.set(conversation_id)


def reset_runtime(graph_token: Token[Any], thread_token: Token[str]) -> None:
    _graph_var.reset(graph_token)
    _thread_var.reset(thread_token)


def drop_thread(conversation_id: str) -> None:
    if conversation_id:
        get_checkpointer().delete_thread(conversation_id)


def read_hitl_interrupt(conversation_id: str | None = None) -> dict[str, Any] | None:
    """读取当前 thread 上挂起的 HITL interrupt 载荷（HITLRequest）。"""
    graph = _graph_var.get(None)
    cid = conversation_id or _thread_var.get(None)
    if graph is None or not cid:
        return None
    snapshot = graph.get_state(thread_config(cid))
    interrupts = list(getattr(snapshot, "interrupts", None) or ())
    if not interrupts:
        for task in getattr(snapshot, "tasks", None) or ():
            interrupts.extend(getattr(task, "interrupts", None) or ())
    for item in interrupts:
        value = getattr(item, "value", item)
        if isinstance(value, dict) and value.get("action_requests"):
            return dict(value)
    return None
