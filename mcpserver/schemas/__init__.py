"""MCP 工具入参/出参 Pydantic 契约。"""

from __future__ import annotations

from schemas.common import ErrorInfo, ToolErrorResult, as_tool_result

__all__ = ["ErrorInfo", "ToolErrorResult", "as_tool_result"]
