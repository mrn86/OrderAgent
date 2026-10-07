from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from app.core.agent.dispatch import slim_dispatch_for_agent
from app.core.agent.loop import _client_steps, _display_answer, _prefer_order_list_reply
from app.core.agent.tools.governance import ResultVerificationError, verify_tool_result

_ROUTER_APP = Path(__file__).resolve().parents[2] / "apps" / "router-agent"
sys.path = [p for p in sys.path if "apps" not in Path(p).as_posix()]
sys.path.insert(0, str(_ROUTER_APP))
for _name in list(sys.modules):
    if _name == "access" or _name.startswith("access."):
        del sys.modules[_name]
_ROUTER_TOOLS = _ROUTER_APP / "tools" / "definitions.py"
_spec = importlib.util.spec_from_file_location("router_tool_definitions", _ROUTER_TOOLS)
assert _spec is not None and _spec.loader is not None
_router_tools = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _router_tools
_spec.loader.exec_module(_router_tools)
DISPATCH_DEFINITIONS = _router_tools.ROUTER_TOOL_DEFINITIONS


def test_slim_dispatch_drops_report_and_progress():
    raw = {
        "ok": True,
        "status": "done",
        "taskId": "t1",
        "expert": "order",
        "progress": [{"type": "tool_end", "observation": {"orderId": "O1"}}],
        "report": {
            "conclusion": "订单运输中",
            "evidence": [{"source": "order_id", "result_hash": "abc"}],
            "commands": [{"tool": "get_order_detail"}],
            "risks": ["注意时效"],
            "unresolved": [],
            "status": "done",
        },
        "verified": {"ok": True, "issues": [], "needSupplement": False, "needReview": False},
        "followUp": None,
    }
    slim = slim_dispatch_for_agent(raw)
    assert slim["conclusion"] == "订单运输中"
    assert slim["risks"] == ["注意时效"]
    assert slim["verified"] == {"ok": True, "issues": []}
    assert "report" not in slim
    assert "progress" not in slim
    assert "followUp" not in slim
    assert "evidence" not in slim
    assert "commands" not in slim
    assert slim["tools"] == ["get_order_detail"]
    checked = verify_tool_result(DISPATCH_DEFINITIONS[0], slim)
    assert checked["conclusion"] == "订单运输中"
    assert checked["tools"] == ["get_order_detail"]
    assert checked["expert"] == "order"
    assert "report" not in checked
    try:
        verify_tool_result(DISPATCH_DEFINITIONS[0], {**slim, "evidence": []})
        raise AssertionError("extra field should fail")
    except ResultVerificationError:
        pass


def test_display_answer_extracts_conclusion_from_json_dump():
    dumped = (
        '{"ok": true, "status": "done", "taskId": "x", "report": '
        '{"conclusion": "快件已到达上海", "evidence": [], "commands": []}, '
        '"verified": {"ok": true, "issues": []}}'
    )
    assert _display_answer(dumped) == "快件已到达上海"


def test_display_answer_falls_back_to_dispatch_conclusions():
    dumped = '{"ok":true,"evidence":[],"result_hash":"a","commands":[]}'
    out = _display_answer(dumped, dispatch_conclusions=["物流运输中"])
    assert out == "物流运输中"


def test_prefer_order_list_over_router_summary():
    listing = (
        "共查到 2 笔订单（本页 2 笔）：\n"
        "1. 订单号 20261001001｜运输中｜实付 299.00 元｜轻跑运动鞋\n"
        "2. 订单号 20261001002｜交易完成｜实付 99.00 元｜速干T恤"
    )
    summary = "已为您查询到全部订单，共 2 笔，合计实付 398.00 元。如需退款请告知订单号。"
    assert _prefer_order_list_reply(summary, [listing]) == listing


def test_prefer_order_list_keeps_reply_that_already_lists_orders():
    listing = "共查到 1 笔订单（本页 1 笔）：\n1. 订单号 20261001001｜运输中｜实付 299.00 元｜鞋"
    reply = "**订单列表**\n\n1. 订单号 20261001001，运输中，实付 299.00 元。"
    assert _prefer_order_list_reply(reply, [listing]) == reply


def test_display_answer_keeps_natural_language():
    text = "**物流状态：运输中**\n\n最新轨迹：已到达上海转运中心。"
    assert _display_answer(text, dispatch_conclusions=["忽略"]) == text


def test_client_steps_only_tool_names():
    steps = [
        {
            "tool": "dispatch_order_expert",
            "input": {"x": 1},
            "observation": {
                "expert": "order",
                "tools": ["get_order_detail"],
                "conclusion": "运输中",
                "report": {"evidence": []},
            },
        },
        {"tool": "escalate_to_human_cs", "input": {"raw": True}, "observation": {"csUrl": "http://x"}},
        {"tool": "", "input": {}},
    ]
    assert _client_steps(steps) == [
        {"tool": "dispatch_order_expert", "expert": "order", "tools": ["get_order_detail"]},
        {"tool": "escalate_to_human_cs"},
    ]
