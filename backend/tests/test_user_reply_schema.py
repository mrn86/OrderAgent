from __future__ import annotations

from app.core.agent.user_reply import RouterUserReply, coerce_user_reply, user_visible_message


def test_schema_ignores_confidence_extra_fields():
    reply = RouterUserReply.model_validate(
        {
            "message": "**物流状态：运输中**\n预计明日送达",
            "confidence": 0.35,
            "verified": {"issues": ["置信度偏低（0.35）"]},
        }
    )
    assert reply.message.startswith("**物流状态")
    assert not hasattr(reply, "confidence") or "confidence" not in reply.model_dump()
    dumped = reply.model_dump()
    assert set(dumped.keys()) == {"message"}
    assert "置信度" not in dumped["message"]


def test_coerce_strips_confidence_lines_from_free_text():
    raw = "**物流状态：运输中**\n物流时效预测的置信度偏低（0.35）\n预计明日送达。"
    out = user_visible_message(raw)
    assert "置信度" not in out
    assert "运输中" in out
    assert "预计明日送达" in out


def test_coerce_prefers_message_field_from_json_dump():
    raw = json_dumps_protocol()
    out = user_visible_message(raw, fallbacks=["回退结论"])
    assert out == "快件已到达上海转运中心"
    assert "confidence" not in out.lower()
    assert "0.35" not in out


def test_coerce_falls_back_to_dispatch_conclusion():
    raw = '{"ok":true,"verified":{"issues":["置信度偏低（0.35）"]},"confidence":0.35}'
    out = user_visible_message(raw, fallbacks=["快件运输中，预计明日送达"])
    assert out == "快件运输中，预计明日送达"


def test_coerce_user_reply_returns_schema_instance():
    reply = coerce_user_reply("订单已发货")
    assert isinstance(reply, RouterUserReply)
    assert reply.message == "订单已发货"


def json_dumps_protocol() -> str:
    import json

    return json.dumps(
        {
            "ok": True,
            "status": "done",
            "confidence": 0.35,
            "message": "快件已到达上海转运中心",
            "verified": {"issues": ["置信度偏低（0.35）"]},
            "report": {"conclusion": "不应优先用这个", "confidence": 0.35},
        },
        ensure_ascii=False,
    )
