"""同步 MCP 工具调用与发现封装。

专家 ToolDefinition.handler 在 ThreadPool 内同步执行，本模块用 asyncio.run
连接 Streamable HTTP MCP Server。测试可通过 set_mcp_tool_caller / set_mcp_list_tools 注入 mock。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

McpToolCaller = Callable[[str, dict[str, Any]], dict[str, Any]]
McpListToolsFn = Callable[[], list["McpToolInfo"]]

_caller_override: McpToolCaller | None = None
_list_override: McpListToolsFn | None = None


@dataclass(frozen=True, slots=True)
class McpToolInfo:
    """MCP list_tools 发现结果的精简视图。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None


def set_mcp_tool_caller(caller: McpToolCaller | None) -> None:
    """注入/清除 MCP 调用实现（测试用）。传 None 恢复默认远程调用。"""
    global _caller_override
    _caller_override = caller


def set_mcp_list_tools(lister: McpListToolsFn | None) -> None:
    """注入/清除 MCP list_tools 实现（测试用）。传 None 恢复默认远程发现。"""
    global _list_override
    _list_override = lister


def call_mcp_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """调用 MCP 工具，返回业务 dict（含 error 结构）。"""
    args = {k: v for k, v in (arguments or {}).items() if v is not None}
    if _caller_override is not None:
        return _caller_override(name, args)
    try:
        return _run_sync(_call_mcp_tool_async(name, args))
    except Exception as exc:  # noqa: BLE001 — 统一成工具可读错误
        logger.exception("MCP tool %s failed", name)
        return {
            "error": {
                "code": 50200,
                "message": f"MCP 调用失败: {type(exc).__name__}: {exc}",
            }
        }


def list_mcp_tools() -> list[McpToolInfo]:
    """从 MCP Server 发现工具清单（name / description / input_schema / output_schema）。"""
    if _list_override is not None:
        return list(_list_override())
    return _run_sync(_list_mcp_tools_async())


def _run_sync(coro: Any) -> T:
    """在无运行 loop 的线程内 asyncio.run；已有 loop 时用独立线程。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _mcp_url() -> str:
    from app.core.config import get_settings

    return (get_settings().mcp_server_url or "").rstrip("/")


async def _call_mcp_tool_async(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from mcp.client.client import Client

    url = await _mcp_url()
    if not url:
        return {"error": {"code": 50201, "message": "mcp_server_url 未配置"}}

    async with Client(url) as client:
        result = await client.call_tool(name, arguments or None)

    if getattr(result, "is_error", False):
        text = _result_text(result)
        return {
            "error": {
                "code": 50202,
                "message": text or f"MCP tool error: {name}",
            }
        }

    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured

    text = _result_text(result)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"result": text}
    if isinstance(parsed, dict):
        return parsed
    return {"result": parsed}


async def _list_mcp_tools_async() -> list[McpToolInfo]:
    from mcp.client.client import Client

    url = await _mcp_url()
    if not url:
        raise RuntimeError("mcp_server_url 未配置，无法发现 MCP 工具")

    async with Client(url) as client:
        tools = await client.list_tools()

    out: list[McpToolInfo] = []
    for tool in tools:
        name = str(getattr(tool, "name", "") or "").strip()
        if not name:
            continue
        description = str(getattr(tool, "description", "") or "").strip()
        schema = getattr(tool, "input_schema", None)
        if schema is None:
            schema = getattr(tool, "inputSchema", None)
        if hasattr(schema, "model_dump"):
            schema = schema.model_dump(by_alias=True, exclude_none=True)
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}}

        out_schema = getattr(tool, "output_schema", None)
        if out_schema is None:
            out_schema = getattr(tool, "outputSchema", None)
        if hasattr(out_schema, "model_dump"):
            out_schema = out_schema.model_dump(by_alias=True, exclude_none=True)
        if not isinstance(out_schema, dict):
            out_schema = None

        out.append(
            McpToolInfo(
                name=name,
                description=description,
                input_schema=schema,
                output_schema=out_schema,
            )
        )
    return out


def _result_text(result: Any) -> str:
    content = getattr(result, "content", None) or []
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            parts.append(str(text))
    return "\n".join(parts).strip()
