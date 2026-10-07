from __future__ import annotations

import json

from app.core.agent.tools.registry import slim_invoice_for_agent


def test_slim_invoice_drops_email_and_pushed_step():
    raw = {
        "invoiceId": "INV20260929001",
        "status": "ISSUED",
        "statusText": "已开票",
        "title": {
            "titleType": "ENTERPRISE",
            "titleName": "某某科技有限公司",
            "taxNo": "91310000MA1XXXXXX",
            "email": "finance@example.com",
        },
        "buyer": {"name": "某公司", "taxNo": "T1", "email": "buyer@example.com"},
        "nested": {"contact": {"eMail": "x@y.com"}},
        "progress": {
            "currentStep": "PUSHED",
            "steps": [
                {
                    "step": "ISSUED",
                    "stepText": "已开具",
                    "status": "DONE",
                    "time": "2026-09-29T10:18:00+08:00",
                },
                {
                    "step": "PUSHED",
                    "stepText": "已发送邮箱",
                    "status": "DONE",
                    "time": "2026-09-29T10:18:05+08:00",
                },
            ],
        },
        "files": [{"type": "PDF", "url": "https://cdn.example.com/a.pdf"}],
    }
    slim = slim_invoice_for_agent(raw)
    text = json.dumps(slim, ensure_ascii=False)
    assert "email" not in slim.get("title", {})
    assert "finance@example.com" not in text
    assert "buyer@example.com" not in text
    assert "x@y.com" not in text
    assert "已发送邮箱" not in text
    assert "PUSHED" not in text
    assert slim["progress"]["currentStep"] == "ISSUED"
    assert all(s.get("step") != "PUSHED" for s in slim["progress"]["steps"])
    assert slim["invoiceId"] == "INV20260929001"
    assert slim["files"]


def test_slim_invoice_preserves_error_without_email():
    raw = {"error": {"code": 50004, "message": "不存在", "email": "a@b.com"}}
    slim = slim_invoice_for_agent(raw)
    assert slim["error"]["code"] == 50004
    assert "email" not in slim["error"]
