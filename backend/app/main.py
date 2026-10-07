from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import build_api_router
from app.core.config import get_settings
from app.core.agent.graph_runtime import ensure_checkpointer
from app.gateway.prompts import ensure_prompt_schema


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_prompt_schema()
    ensure_checkpointer()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="1.5.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Retry-After"],
    )
    app.include_router(build_api_router(), prefix=settings.api_prefix)
    return app


app = create_app()
