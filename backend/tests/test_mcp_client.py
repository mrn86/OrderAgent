"""MCP 客户端封装与 mock 注入。"""

from __future__ import annotations

from app.core.agent.tools.mcp_client import (
    McpToolInfo,
    call_mcp_tool,
    list_mcp_tools,
    set_mcp_list_tools,
    set_mcp_tool_caller,
)


def test_set_mcp_tool_caller_override():
    def fake(name: str, arguments: dict) -> dict:
        return {"ok": True, "tool": name, "args": arguments}

    set_mcp_tool_caller(fake)
    try:
        out = call_mcp_tool("query_orders", {"page": 1, "order_no": None})
        assert out["ok"] is True
        assert out["tool"] == "query_orders"
        assert out["args"] == {"page": 1}
    finally:
        set_mcp_tool_caller(None)


def test_call_mcp_tool_strips_none_args():
    seen: dict = {}

    def fake(name: str, arguments: dict) -> dict:
        seen["name"] = name
        seen["arguments"] = arguments
        return {"list": []}

    set_mcp_tool_caller(fake)
    try:
        call_mcp_tool("list_refunds", {"order_id": "O1", "order_no": None})
        assert seen["arguments"] == {"order_id": "O1"}
    finally:
        set_mcp_tool_caller(None)


def test_list_mcp_tools_override():
    set_mcp_list_tools(
        lambda: [
            McpToolInfo(
                name="query_orders",
                description="list orders",
                input_schema={"type": "object", "properties": {"page": {"type": "integer"}}},
            )
        ]
    )
    try:
        tools = list_mcp_tools()
        assert len(tools) == 1
        assert tools[0].name == "query_orders"
        assert tools[0].description == "list orders"
    finally:
        set_mcp_list_tools(None)
