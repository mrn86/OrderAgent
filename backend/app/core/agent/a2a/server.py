"""在专家 FastAPI 上挂载 A2A JSON-RPC / AgentCard。"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from a2a.server.request_handlers import LegacyRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import DatabaseTaskStore, InMemoryTaskStore

from app.core.agent.a2a.card import build_expert_agent_card
from app.core.agent.a2a.executor import ExpertAgentExecutor
from app.core.agent.profiles import AgentProfile
from app.core.database.db import get_async_engine

logger = logging.getLogger(__name__)

A2A_TASK_TABLE = "a2a_tasks"


def _task_store():
    """优先数据库；依赖或引擎建不起来时用内存，避免专家进程起不来。"""
    try:
        return DatabaseTaskStore(get_async_engine(), table_name=A2A_TASK_TABLE)
    except Exception:
        logger.warning("无法创建 DatabaseTaskStore，使用内存任务库", exc_info=True)
        return InMemoryTaskStore()


def mount_a2a(app: FastAPI, profile: AgentProfile) -> LegacyRequestHandler:
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
    logger.info(
        "A2A mounted agent=%s interfaces=%s",
        card.name,
        [i.url for i in card.supported_interfaces],
    )
    return handler
