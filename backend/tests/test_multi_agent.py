from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

from app.core.agent.bus import reset_task_bus, use_memory_bus
from app.core.agent.dispatch import dispatch_expert, send_control
from app.core.agent.profiles import current_profile, expert_thread_id, install_process_profile
from app.core.agent.protocol import ExpertReport, canonical_hash, report_from_answer
from app.core.agent.verify import verify_report
from app.core.audit.task import build_agent_task_record
from app.core.agent.tools.mcp_client import set_mcp_tool_caller

_APPS = Path(__file__).resolve().parents[2] / "apps"


def _load_access(app_name: str):
    path = _APPS / app_name / "access" / "config.py"
    spec = importlib.util.spec_from_file_location(f"{app_name}_access_config", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def setup_function() -> None:
    reset_task_bus()
    use_memory_bus()


def teardown_function() -> None:
    reset_task_bus()


def test_profiles_split_tools():
    router = _load_access("router-agent").ALLOWED_TOOLS
    order = _load_access("order-expert").ALLOWED_TOOLS
    logistics = _load_access("logistics-expert").ALLOWED_TOOLS
    invoice = _load_access("invoice-expert").ALLOWED_TOOLS
    assert "dispatch_order_expert" in router
    assert "dispatch_logistics_expert" in router
    assert "query_orders" not in router
    assert "query_orders" in order
    assert "get_logistics_tracking" not in order
    assert "get_logistics_tracking" in logistics
    assert "get_order_by_no" not in logistics
    assert "get_order_detail" not in logistics
    assert "create_refund" not in logistics
    assert "get_invoice" not in order
    assert "get_invoice" in invoice
    assert "create_refund" not in invoice
    assert "escalate_to_human_cs" in router
    assert "escalate_to_human_cs" in order
    assert "escalate_to_human_cs" in logistics
    assert "escalate_to_human_cs" in invoice
    order_access = _load_access("order-expert")
    install_process_profile(
        role="order",
        prompt_key="order_expert_system",
        expert_name="order",
        agent_id="order-expert",
        tools=order,
        permissions=order_access.PERMISSIONS,
    )
    profile = current_profile()
    assert profile.tools == order
    assert profile.expert_name == "order"
    assert "order:read" in profile.permissions
    tid = expert_thread_id("c1", "order-expert", "t1")
    assert tid == "c1:order-expert:t1"


def test_report_from_free_text():
    report = report_from_answer("物流运输中", task_id="t", expert="order")
    assert report.conclusion == "物流运输中"
    assert report.status == "need_more_info"
    assert report.confidence < 0.5


def test_dispatch_and_report_roundtrip():
    def fake_send(envelope):
        return {
            "type": "report",
            "payload": ExpertReport(
                conclusion="订单运输中",
                evidence=[],
                confidence=0.9,
                task_id=envelope.task_id,
                expert="order",
            ).model_dump(),
        }

    with patch("app.core.agent.dispatch.send_dispatch", side_effect=fake_send):
        result = dispatch_expert(
            expert="order",
            instruction="查订单 2026092012345678",
            reason="unit-test",
            conversation_id="conv-1",
            verify=False,
        )
    assert result["ok"] is True
    assert result["conclusion"] == "订单运输中"
    assert "report" not in result
    assert "progress" not in result


def test_dispatch_logistics_roundtrip():
    def fake_send(envelope):
        return {
            "type": "report",
            "payload": ExpertReport(
                conclusion="快件运输中",
                evidence=[],
                confidence=0.9,
                task_id=envelope.task_id,
                expert="logistics",
            ).model_dump(),
        }

    with patch("app.core.agent.dispatch.send_dispatch", side_effect=fake_send):
        result = dispatch_expert(
            expert="logistics",
            instruction="查物流 2026092012345678",
            reason="unit-test",
            conversation_id="conv-2",
            verify=False,
        )
    assert result["ok"] is True
    assert result["conclusion"] == "快件运输中"
    assert result["expert"] == "logistics"
    assert "report" not in result


def test_send_control_resume_via_a2a():
    from app.core.agent.bus import save_meta

    save_meta("task-hitl", {"expert": "order", "conversation_id": "c-hitl"})

    def fake_resume(expert, task_id, action):
        assert expert == "order"
        assert task_id == "task-hitl"
        assert action == "approve"
        return {
            "type": "report",
            "payload": {"conclusion": "已退款", "task_id": task_id, "expert": "order"},
        }

    with patch("app.core.agent.dispatch.resume_via_http", side_effect=fake_resume):
        out = send_control("task-hitl", "approve", "c-hitl")
    assert out.get("answer") == "已退款"
    assert out.get("taskId") == "task-hitl"


def test_verify_detects_missing_and_hash_mismatch():
    bad = ExpertReport(
        conclusion="x",
        evidence=[{"source": "order_id", "id": "NOPE", "result_hash": "abc"}],
        confidence=0.9,
    )
    verdict = verify_report(bad)
    assert verdict.ok is False
    assert verdict.need_review or any("无法复核" in i for i in verdict.issues)

    mcp_root = Path(__file__).resolve().parents[2] / "mcpserver"
    if str(mcp_root) not in sys.path:
        sys.path.insert(0, str(mcp_root))
    from data import fake_data as mcp_fake_data

    order = mcp_fake_data.get_order_by_id("O20261002002")
    assert order is not None

    def _mcp_get(name: str, arguments: dict):
        if name == "get_order_detail" and arguments.get("order_id") == "O20261002002":
            return order
        return {"error": {"code": 404, "message": "not found"}}

    set_mcp_tool_caller(_mcp_get)
    try:
        good = ExpertReport(
            conclusion="ok",
            evidence=[
                {
                    "source": "order_id",
                    "id": "O20261002002",
                    "result_hash": canonical_hash(order),
                }
            ],
            confidence=0.9,
            commands=[{"tool": "get_order_detail", "args": {}, "result_hash": "x"}],
        )
        ok = verify_report(good)
        assert ok.ok is True
    finally:
        set_mcp_tool_caller(None)


def test_verify_low_confidence_needs_supplement():
    report = ExpertReport(conclusion="maybe", confidence=0.2, status="done")
    verdict = verify_report(report)
    assert verdict.ok is False
    assert verdict.need_supplement is True
    assert verdict.need_review is False
    record = build_agent_task_record(
        phase="created",
        reason="route_to_order",
        input_summary="查订单 2026092012345678",
        output_summary="运输中",
        task_id="t1",
        expert="order",
        conversation_id="c1",
        latency_ms=12.5,
        tool_calls=2,
    )
    assert record["kind"] == "agent_task"
    assert record["reason"] == "route_to_order"
    assert record["input_summary"]
    assert record["task_id"] == "t1"
