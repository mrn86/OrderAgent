from __future__ import annotations

from app.core.audit.redact import redact_text, redact_value
from app.core.audit.schema import build_agent_turn_record
from app.core.audit.sink import emit_record


def test_redact_text_covers_former_pii_middleware_types():
    raw = (
        "联系 13800138000 或 user@example.com，"
        "证件 110101199003078890，卡 4111111111111111，"
        "图 http://cdn.example.com/a.png"
    )
    out = redact_text(raw)
    assert "13800138000" not in out
    assert "user@example.com" not in out
    assert "110101199003078890" not in out
    assert "4111111111111111" not in out
    assert "http://cdn.example.com/a.png" not in out
    assert "[REDACTED_CN_MOBILE]" in out
    assert "[REDACTED_EMAIL]" in out
    assert "[REDACTED_CN_ID]" in out
    assert "[REDACTED_CREDIT_CARD]" in out
    assert "[REDACTED_URL]" in out


def test_redact_value_masks_secret_keys():
    out = redact_value({"api_key": "sk-live", "note": "hi user@x.com"})
    assert out["api_key"] == "***"
    assert "[REDACTED_EMAIL]" in out["note"]


def test_agent_turn_record_redacts_tools_and_model_result():
    record = build_agent_turn_record(
        {
            "audit_request_id": "r1",
            "trace_id": "t1",
            "user_id": "u1",
            "conversation_id": "c1",
            "tools": [
                {
                    "name": "query_orders",
                    "arguments": {"phone": "13912345678", "password": "secret"},
                    "ok": True,
                    "error_code": None,
                    "model": None,
                }
            ],
            "model_result": "回电 13912345678",
            "agent_rounds": 1,
            "status": "done",
        }
    )
    assert record["tools"][0]["arguments"]["password"] == "***"
    assert "13912345678" not in record["tools"][0]["arguments"]["phone"]
    assert "13912345678" not in (record["model_result"] or "")


def test_emit_record_redacts_before_write():
    captured: list[dict] = []

    class Capture:
        def write(self, record):
            captured.append(dict(record))

    from app.core.audit import sink as sink_mod

    old = sink_mod._default_sink
    sink_mod._default_sink = Capture()
    try:
        emit_record({"kind": "agent_turn", "note": "mail a@b.com"})
    finally:
        sink_mod._default_sink = old
    assert captured
    assert "a@b.com" not in captured[0]["note"]
