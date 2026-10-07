from __future__ import annotations

from unittest.mock import patch

from app.core.agent.bus import reset_task_bus, use_memory_bus
from app.core.agent.dispatch import dispatch_expert, send_control
from app.core.agent.profiles import expert_thread_id, profile_for_role
from app.core.agent.protocol import ExpertReport, canonical_hash, report_from_answer
from app.core.agent.verify import verify_report
from app.core.audit.task import build_agent_task_record
from app.core import fake_data


def setup_function() -> None:
    reset_task_bus()
    use_memory_bus()


def teardown_function() -> None:
    reset_task_bus()


def test_profiles_split_tools():
    router = profile_for_role("router")
    order = profile_for_role("order")
    logistics = profile_for_role("logistics")
    invoice = profile_for_role("invoice")
    assert "dispatch_order_expert" in router.tools
    assert "dispatch_logistics_expert" in router.tools
    assert "query_orders" not in router.tools
    assert "query_orders" in order.tools
    assert "get_logistics_tracking" not in order.tools
    assert "get_logistics_tracking" in logistics.tools
    assert "create_refund" not in logistics.tools
    assert "get_invoice" not in order.tools
    assert "get_invoice" in invoice.tools
    assert "create_refund" not in invoice.tools
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

    order = fake_data.get_order_by_id("O20260920001")
    good = ExpertReport(
        conclusion="ok",
        evidence=[
            {
                "source": "order_id",
                "id": "O20260920001",
                "result_hash": canonical_hash(order),
            }
        ],
        confidence=0.9,
        commands=[{"tool": "get_order_detail", "args": {}, "result_hash": "x"}],
    )
    ok = verify_report(good)
    assert ok.ok is True


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
