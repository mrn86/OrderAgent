"""Agent 对外入口：HTTP/SSE、会话、LiteLLM Router、限流、提示词模板。

注意：勿在包初始化时 eager import routes/service，以免与 agent.loop 循环依赖。
"""

from typing import Any

__all__ = ["router", "sse_router"]


def __getattr__(name: str) -> Any:
    if name in {"router", "sse_router"}:
        from app.gateway import routes as _routes

        return getattr(_routes, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
