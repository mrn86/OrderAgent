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
from a2a.server.tasks import InMemoryTaskStore

from app.core.agent.a2a_card import build_expert_agent_card
from app.core.agent.a2a_executor import ExpertAgentExecutor
from app.core.agent.profiles import AgentProfile

logger = logging.getLogger(__name__)


def mount_a2a(app: FastAPI, profile: AgentProfile) -> LegacyRequestHandler:
    card = build_expert_agent_card(profile)
    handler = LegacyRequestHandler(
        agent_executor=ExpertAgentExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/"),
    )
    app.state.a2a_handler = handler
    logger.info(
        "A2A mounted agent=%s interfaces=%s",
        card.name,
        [i.url for i in card.supported_interfaces],
    )
    return handler
