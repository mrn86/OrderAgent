"""专家进程入口：健康检查 + A2A Server。不对用户暴露 chat。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.core.agent.a2a_server import mount_a2a
from app.core.agent.expert_worker import resume_expert_task
from app.core.agent.graph_runtime import ensure_checkpointer
from app.core.agent.profiles import current_profile
from app.core.config import get_settings
from app.gateway.prompts import ensure_prompt_schema


class A2AResumeBody(BaseModel):
    taskId: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_prompt_schema()
    ensure_checkpointer()
    yield
    handler = getattr(app.state, "a2a_handler", None)
    if handler is not None and hasattr(handler, "aclose"):
        await handler.aclose()


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
    mount_a2a(app, profile)

    @app.get("/v1/health")
    def health():
        return {
            "ok": True,
            "role": profile.role,
            "agentId": profile.agent_id,
            "app": settings.app_name,
            "transport": "a2a",
        }

    @app.post("/v1/a2a/resume")
    async def a2a_resume(body: A2AResumeBody) -> dict[str, Any]:
        return await resume_expert_task(body.taskId.strip(), body.action.strip())

    return app


app = create_expert_app()
