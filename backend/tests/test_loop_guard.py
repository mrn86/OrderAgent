from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.agent.loop_guard import (
    ToolLoopGuardMiddleware,
    strip_tool_calls_from_response,
    tool_call_fingerprint,
)
from app.core.agent.tools.registry import _slim_order_list_for_agent


def test_fingerprint_stable():
    a = tool_call_fingerprint("query_orders", {"page": 1, "page_size": 10})
    b = tool_call_fingerprint("query_orders", {"page_size": 10, "page": 1})
    assert a == b
    assert a != tool_call_fingerprint("query_orders", {"page": 2, "page_size": 10})


def test_strip_tool_calls_from_ai_message():
    msg = AIMessage(
        content="先查一下",
        tool_calls=[{"name": "query_orders", "args": {}, "id": "c1", "type": "tool_call"}],
    )
    out = strip_tool_calls_from_response(msg)
    assert isinstance(out, AIMessage)
    assert not (out.tool_calls or [])
    assert "先查一下" in out.content


def test_duplicate_tool_short_circuit():
    guard = ToolLoopGuardMiddleware()
    first = ToolMessage(
        content='{"list":[{"orderId":"O1"}],"total":1}',
        tool_call_id="a",
        name="query_orders",
    )
    guard._remember_if_ok(tool_call_fingerprint("query_orders", {}), first)

    class Req:
        tool_call = {"name": "query_orders", "args": {}, "id": "b"}

    called = {"n": 0}

    def handler(_req):
        called["n"] += 1
        return first

    result = guard.wrap_tool_call(Req(), handler)  # type: ignore[arg-type]
    assert called["n"] == 0
    assert isinstance(result, ToolMessage)
    assert "已经成功" in result.content or "已用相同参数" in result.content


def test_error_result_not_cached_as_ok():
    guard = ToolLoopGuardMiddleware()
    err = ToolMessage(
        content='{"ok":false,"error_code":"INVALID_ARGUMENT","message":"bad"}',
        tool_call_id="a",
        name="query_orders",
    )
    key = tool_call_fingerprint("query_orders", {"page": 1})
    guard._remember_if_ok(key, err)
    assert key not in guard._ok_results


def test_slim_order_list_drops_nested_payload():
    raw = {
        "list": [
            {
                "orderId": "O1",
                "orderNo": "2026092012345678",
                "status": "SHIPPED",
                "statusText": "运输中",
                "createdAt": "2026-09-20",
                "payAmount": 29900,
                "items": [{"spuName": "手机壳", "imageUrl": "http://x/y.png", "unitPrice": 1}],
                "receiver": {"nameMask": "张*"},
            }
        ],
        "page": 1,
        "total": 1,
        "hasMore": False,
    }
    slim = _slim_order_list_for_agent(raw)
    row = slim["list"][0]
    assert "receiver" not in row
    assert "imageUrl" not in row
    assert row["itemNames"] == ["手机壳"]
    assert slim["total"] == 1


def test_after_model_ends_when_same_tool_already_succeeded():
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    guard = ToolLoopGuardMiddleware()
    key = tool_call_fingerprint("query_orders", {})
    guard._ok_results[key] = '{"list":[]}'
    last = AIMessage(
        content="再查一次",
        id="ai-2",
        tool_calls=[{"name": "query_orders", "args": {}, "id": "c2", "type": "tool_call"}],
    )
    state = {
        "messages": [
            HumanMessage(content="查看全部订单"),
            AIMessage(
                content="",
                tool_calls=[{"name": "query_orders", "args": {}, "id": "c1", "type": "tool_call"}],
            ),
            ToolMessage(content='{"list":[]}', tool_call_id="c1", name="query_orders"),
            last,
        ]
    }
    update = guard.after_model(state, None)
    assert update is not None
    assert update.get("jump_to") == "end"
    msgs = update.get("messages") or []
    assert any(isinstance(m, AIMessage) and not (m.tool_calls or []) for m in msgs)


def test_agent_graph_has_no_pii_middleware_nodes():
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    from app.core.context.compression import ContextCompressionMiddleware
    from app.core.agent.loop_guard import ToolLoopGuardMiddleware

    model = FakeListChatModel(responses=["好的"])
    agent = create_agent(
        model=model,
        tools=[],
        middleware=[ContextCompressionMiddleware(), ToolLoopGuardMiddleware()],
    )
    compiled = getattr(agent, "bound", agent)
    nodes = compiled.get_graph().nodes
    assert not any("PII" in str(n) for n in nodes)
