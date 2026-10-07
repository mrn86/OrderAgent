"""专家终态：强制提交 ExpertReport。"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from pydantic import Field

from app.core.agent.protocol import CommandRecord, EvidenceItem, ExpertReport, PathStep
from app.core.agent.profiles import SUBMIT_REPORT
from app.core.agent.tools.governance import Effect, Risk, StrictArgs, ToolDefinition, ToolPolicy
from app.core.agent.tools.permissions import PERM_CS_ESCALATE

_last_report: ContextVar[ExpertReport | None] = ContextVar("expert_report", default=None)


class SubmitExpertReportArgs(StrictArgs):
    conclusion: str = Field(..., min_length=1, max_length=4000)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    path: list[dict[str, Any]] = Field(default_factory=list)
    commands: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    unresolved: list[str] = Field(default_factory=list)
    suggested_next: list[str] = Field(default_factory=list)
    status: str = Field(default="done")


def get_submitted_report() -> ExpertReport | None:
    return _last_report.get()


def clear_submitted_report() -> None:
    _last_report.set(None)


def _submit(args: SubmitExpertReportArgs) -> dict[str, Any]:
    evidence = []
    for item in args.evidence:
        if isinstance(item, dict):
            evidence.append(EvidenceItem.model_validate(item))
    path = []
    for item in args.path:
        if isinstance(item, dict):
            path.append(PathStep.model_validate(item))
    commands = []
    for item in args.commands:
        if isinstance(item, dict):
            commands.append(CommandRecord.model_validate(item))
    status = args.status if args.status in {"done", "failed", "need_hitl", "need_more_info"} else "done"
    report = ExpertReport(
        conclusion=args.conclusion,
        evidence=evidence,
        path=path,
        commands=commands,
        risks=list(args.risks),
        confidence=args.confidence,
        unresolved=list(args.unresolved),
        suggested_next=list(args.suggested_next),
        status=status,  # type: ignore[arg-type]
    )
    _last_report.set(report)
    return {"ok": True, "accepted": True, "conclusion": report.conclusion}


SUBMIT_REPORT_DEFINITION = ToolDefinition(
    name=SUBMIT_REPORT,
    description=(
        "提交本任务的结构化专家报告（必须在结束前调用一次）。"
        "字段：conclusion, evidence[{source,id,excerpt,result_hash}], path, commands, "
        "risks, confidence(0-1), unresolved, suggested_next, status。"
        "evidence.source 用 order_id / order_no / invoice_id / refund_id / after_sale_id。"
    ),
    parameters_model=SubmitExpertReportArgs,
    policy=ToolPolicy(
        effect=Effect.READ,
        risk=Risk.LOW,
        permission=PERM_CS_ESCALATE,
        timeout_seconds=3.0,
        max_retries=0,
        idempotent=True,
    ),
    handler=_submit,  # type: ignore[arg-type]
)
