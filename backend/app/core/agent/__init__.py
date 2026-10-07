"""Agent 核心包：LangChain AgentLoop、工具注册、LLM 与人工客服兜底。

对外主要导出：
- run_agent_loop: 同步完整执行（非流式）
- stream_agent_loop: 异步事件流（供 SSE / EventSource 使用）

按需导出，避免导入 graph_runtime 等子模块时立刻拉起 loop，
再被 context.compression 绕回形成循环导入。
"""

from typing import Any

__all__ = ["run_agent_loop", "stream_agent_loop"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from app.core.agent.loop import run_agent_loop, stream_agent_loop

        return {"run_agent_loop": run_agent_loop, "stream_agent_loop": stream_agent_loop}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
