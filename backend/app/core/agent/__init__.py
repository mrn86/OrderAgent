"""Agent 核心包：LangChain AgentLoop、工具注册、LLM 与人工客服兜底。

对外主要导出：
- run_agent_loop: 同步完整执行（非流式）
- stream_agent_loop: 异步事件流（供 SSE / EventSource 使用）
"""

from app.core.agent.loop import run_agent_loop, stream_agent_loop

__all__ = ["run_agent_loop", "stream_agent_loop"]
