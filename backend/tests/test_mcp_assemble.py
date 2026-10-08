"""MCP 发现装配 ToolDefinition。"""

from __future__ import annotations

import pytest

from app.core.agent.tools.governance import Effect, Risk, ToolPolicy, invoke_tool
from app.core.agent.tools.mcp_assemble import (
    ToolSpec,
    assemble_mcp_tool_definitions,
    parameters_model_from_json_schema,
    result_model_from_json_schema,
)
from app.core.agent.tools.mcp_client import (
    McpToolInfo,
    set_mcp_list_tools,
    set_mcp_tool_caller,
)
from app.core.agent.tools.permissions import ExecutionContext, PermissionMode


def _policy() -> ToolPolicy:
    return ToolPolicy(
        effect=Effect.READ,
        risk=Risk.LOW,
        permission="order:read",
        timeout_seconds=5.0,
        max_retries=0,
        idempotent=True,
    )


def test_parameters_model_from_json_schema_required_and_optional():
    model = parameters_model_from_json_schema(
        "demo_tool",
        {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "page": {"type": "integer", "default": 1},
                "include_eta": {"type": "boolean", "default": True},
            },
            "required": ["order_id"],
        },
    )
    inst = model(order_id="O1")
    assert inst.order_id == "O1"
    assert inst.page == 1
    assert inst.include_eta is True


def test_parameters_model_from_json_schema_constraints():
    model = parameters_model_from_json_schema(
        "create_refund",
        {
            "type": "object",
            "properties": {
                "amount": {"type": "integer", "minimum": 1},
                "reason": {"type": "string", "minLength": 4, "maxLength": 200},
            },
            "required": ["amount", "reason"],
        },
    )
    ok = model(amount=100, reason="质量问题")
    assert ok.amount == 100
    with pytest.raises(Exception):
        model(amount=0, reason="质量问题")
    with pytest.raises(Exception):
        model(amount=100, reason="abc")


def test_result_model_from_json_schema_allows_error_and_extra():
    model = result_model_from_json_schema(
        "query_orders",
        {
            "type": "object",
            "properties": {
                "list": {"type": "array"},
                "page": {"type": "integer"},
                "total": {"type": "integer"},
            },
        },
    )
    success = model.model_validate({"list": [], "page": 1, "total": 0, "slim": True})
    assert success.page == 1
    err = model.model_validate({"error": {"code": 1, "message": "x"}})
    assert err.error["code"] == 1


def test_assemble_mcp_tool_definitions_success():
    set_mcp_list_tools(
        lambda: [
            McpToolInfo(
                name="query_orders",
                description="远端订单列表描述",
                input_schema={
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer", "default": 1},
                        "page_size": {"type": "integer", "default": 10},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "list": {"type": "array"},
                        "page": {"type": "integer"},
                    },
                },
            )
        ]
    )
    set_mcp_tool_caller(lambda name, args: {"tool": name, "args": args, "list": []})
    try:
        defs = assemble_mcp_tool_definitions(
            [ToolSpec("query_orders", _policy(), postprocess=lambda d: {**d, "slim": True})]
        )
        assert len(defs) == 1
        assert defs[0].name == "query_orders"
        assert defs[0].description == "远端订单列表描述"

        ctx = ExecutionContext(
            trace_id="t1",
            user_id="u1",
            tenant_id="default",
            permissions=frozenset({"order:read"}),
            allowed_tools=frozenset({"query_orders"}),
            mode=PermissionMode.DEFAULT,
            conversation_id="c1",
        )
        raw = invoke_tool(defs[0], {"page": 2}, ctx=ctx)
        assert "query_orders" in raw
        assert "slim" in raw
    finally:
        set_mcp_list_tools(None)
        set_mcp_tool_caller(None)


def test_assemble_missing_tool_raises():
    set_mcp_list_tools(lambda: [])
    try:
        with pytest.raises(RuntimeError, match="query_orders"):
            assemble_mcp_tool_definitions([ToolSpec("query_orders", _policy())])
    finally:
        set_mcp_list_tools(None)
