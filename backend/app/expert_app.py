"""专家进程入口：健康检查。A2A 由各专家进程自己挂载。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.agent.graph_runtime import ensure_checkpointer
from app.core.agent.profiles import current_profile
from app.core.config import get_settings
from app.core.database.db import dispose_async_engine
from app.gateway.prompts import ensure_prompt_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_prompt_schema()
    ensure_checkpointer()
    startup = getattr(app.state, "a2a_startup", None)
    if startup is not None:
        await startup()
    yield
    shutdown = getattr(app.state, "a2a_shutdown", None)
    if shutdown is not None:
        await shutdown()
    await dispose_async_engine()


def create_expert_app() -> FastAPI:
    settings = get_settings()
    profile = current_profile()
    app = FastAPI(title=profile.agent_name, version="1.5.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/v1/health")
    def health():
        live = current_profile()
        return {
            "ok": True,
            "role": live.role,
            "agentId": live.agent_id,
            "app": settings.app_name,
            "transport": "a2a",
        }

    return app


app = create_expert_app()
