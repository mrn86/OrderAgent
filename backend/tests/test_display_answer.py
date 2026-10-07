from __future__ import annotations

from app.core.agent.dispatch import slim_dispatch_for_agent
from app.core.agent.loop import _client_steps, _display_answer


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


def test_display_answer_keeps_natural_language():
    text = "**物流状态：运输中**\n\n最新轨迹：已到达上海转运中心。"
    assert _display_answer(text, dispatch_conclusions=["忽略"]) == text


def test_client_steps_only_tool_names():
    steps = [
        {"tool": "dispatch_order_expert", "input": {"x": 1}, "observation": {"huge": True}},
        {"tool": "", "input": {}},
    ]
    assert _client_steps(steps) == [{"tool": "dispatch_order_expert"}]
