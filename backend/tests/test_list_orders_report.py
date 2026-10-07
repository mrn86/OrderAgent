from __future__ import annotations

from app.core.agent.protocol import (
    ExpertReport,
    conclusion_from_query_orders_steps,
    report_from_answer,
    upgrade_report_with_list_steps,
)
from app.core.agent.verify import verify_report


def _list_steps() -> list[dict]:
    return [
        {
            "tool": "query_orders",
            "input": {"page": 1, "page_size": 10},
            "observation": {
                "list": [
                    {
                        "orderId": "O1",
                        "orderNo": "20261001001",
                        "status": "SHIPPING",
                        "statusText": "运输中",
                        "payAmount": 29900,
                        "itemNames": ["轻跑运动鞋"],
                    },
                    {
                        "orderId": "O2",
                        "orderNo": "20261001002",
                        "status": "COMPLETED",
                        "statusText": "交易完成",
                        "payAmount": 9900,
                        "itemNames": ["速干T恤"],
                    },
                ],
                "total": 2,
                "page": 1,
                "pageSize": 10,
            },
        }
    ]


def test_conclusion_from_query_orders_steps():
    text = conclusion_from_query_orders_steps(_list_steps())
    assert text is not None
    assert "共查到 2 笔" in text
    assert "20261001001" in text
    assert "299.00" in text


def test_report_from_answer_uses_list_when_unstructured():
    report = report_from_answer("", task_id="t", expert="order", steps=_list_steps())
    assert report.status == "done"
    assert report.confidence >= 0.8
    assert "20261001001" in report.conclusion


def test_upgrade_replaces_ask_for_phone_conclusion():
    report = ExpertReport(
        conclusion="订单专家未能返回有效结果，需要补充信息。请提供订单号或手机号。",
        status="need_more_info",
        confidence=0.3,
        commands=[{"tool": "query_orders", "args": {}, "ok": True}],
    )
    upgraded = upgrade_report_with_list_steps(report, _list_steps())
    assert upgraded.status == "done"
    assert "手机号" not in upgraded.conclusion
    assert "20261001001" in upgraded.conclusion


def test_verify_accepts_successful_query_orders_without_evidence():
    report = ExpertReport(
        conclusion="共查到 2 笔订单",
        confidence=0.4,
        status="need_more_info",
        commands=[{"tool": "query_orders", "args": {}, "ok": True, "result_hash": "x"}],
    )
    verdict = verify_report(report)
    assert verdict.ok is True
    assert verdict.need_supplement is False
