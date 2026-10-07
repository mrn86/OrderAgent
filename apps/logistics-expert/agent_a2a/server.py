"""在本专家 FastAPI 上挂载 A2A JSON-RPC / AgentCard / HITL resume。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from a2a.server.request_handlers import LegacyRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import DatabaseTaskStore, InMemoryTaskStore

from agent_a2a.card import build_expert_agent_card
from agent_a2a.executor import ExpertAgentExecutor
from app.core.database.db import get_async_engine

logger = logging.getLogger(__name__)

A2A_TASK_TABLE = "a2a_tasks"


class A2AResumeBody(BaseModel):
    taskId: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)


def _task_store():
    """优先数据库；依赖或引擎建不起来时用内存，避免专家进程起不来。"""
    try:
        return DatabaseTaskStore(get_async_engine(), table_name=A2A_TASK_TABLE)
    except Exception:
        logger.warning("无法创建 DatabaseTaskStore，使用内存任务库", exc_info=True)
        return InMemoryTaskStore()


def _use_memory_task_store(app: FastAPI) -> None:
    memory = InMemoryTaskStore()
    app.state.a2a_task_store = memory
    handler = getattr(app.state, "a2a_handler", None)
    if handler is None:
        return
    handler.task_store = memory
    builder = getattr(handler, "_request_context_builder", None)
    if builder is not None and hasattr(builder, "_task_store"):
        builder._task_store = memory


def install_expert_a2a(app: FastAPI) -> LegacyRequestHandler:
    """挂载本进程的 A2A Server，并登记启动/关闭钩子供 expert_app lifespan 调用。"""
    from app.core.agent.profiles import current_profile

    profile = current_profile()
    card = build_expert_agent_card(profile)
    store = _task_store()
    handler = LegacyRequestHandler(
        agent_executor=ExpertAgentExecutor(),
        task_store=store,
        agent_card=card,
    )
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/"),
    )
    app.state.a2a_handler = handler
    app.state.a2a_task_store = store

    async def startup() -> None:
        current = getattr(app.state, "a2a_task_store", None)
        if current is None or not hasattr(current, "initialize"):
            return
        try:
            await current.initialize()
            logger.info("A2A task store=database table=%s", A2A_TASK_TABLE)
        except Exception:
            logger.warning("A2A DatabaseTaskStore 不可用，回退内存任务库", exc_info=True)
            _use_memory_task_store(app)

    async def shutdown() -> None:
        current_handler = getattr(app.state, "a2a_handler", None)
        if current_handler is not None and hasattr(current_handler, "aclose"):
            await current_handler.aclose()

    app.state.a2a_startup = startup
    app.state.a2a_shutdown = shutdown

    @app.post("/v1/a2a/resume")
    async def a2a_resume(body: A2AResumeBody) -> dict[str, Any]:
        from app.core.agent.expert_worker import resume_expert_task

        return await resume_expert_task(body.taskId.strip(), body.action.strip())

    logger.info(
        "A2A mounted agent=%s interfaces=%s",
        card.name,
        [i.url for i in card.supported_interfaces],
    )
    return handler
