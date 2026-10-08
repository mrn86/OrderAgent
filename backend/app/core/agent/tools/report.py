"""专家终态：强制提交 ExpertReport。"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Literal

from pydantic import ConfigDict, Field

from app.core.agent.protocol import CommandRecord, EvidenceItem, ExpertReport, PathStep, ReportStatus
from app.core.agent.tools.governance import (
    Effect,
    Risk,
    StrictArgs,
    StrictResult,
    ToolDefinition,
    ToolPolicy,
)

SUBMIT_REPORT = "submit_expert_report"

_last_report: ContextVar[ExpertReport | None] = ContextVar("expert_report", default=None)

# 证据源由各域自行约定；平台不再用 Literal 写死
EvidenceSource = str


class _ReportPart(StrictArgs):
    """报告嵌套字段：与工具参数一样拒绝未声明键。"""


class SubmitEvidence(_ReportPart):
    source: EvidenceSource
    id: str = ""
    excerpt: str = ""
    result_hash: str = ""


class SubmitPathStep(_ReportPart):
    step: str
    detail: str = ""


class SubmitCommand(_ReportPart):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    result_hash: str = ""
    ok: bool = True


class SubmitExpertReportArgs(StrictArgs):
    conclusion: str = Field(..., min_length=1, max_length=4000)
    evidence: list[SubmitEvidence] = Field(default_factory=list)
    path: list[SubmitPathStep] = Field(default_factory=list)
    commands: list[SubmitCommand] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    unresolved: list[str] = Field(default_factory=list)
    suggested_next: list[str] = Field(default_factory=list)
    status: ReportStatus = "done"


class SubmitExpertReportResult(StrictResult):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True]
    accepted: Literal[True]
    conclusion: str


def get_submitted_report() -> ExpertReport | None:
    return _last_report.get()


def clear_submitted_report() -> None:
    _last_report.set(None)


def _submit(args: SubmitExpertReportArgs) -> dict[str, Any]:
    report = ExpertReport(
        conclusion=args.conclusion,
        evidence=[
            EvidenceItem(
                source=item.source,
                id=item.id,
                excerpt=item.excerpt,
                result_hash=item.result_hash,
            )
            for item in args.evidence
        ],
        path=[PathStep(step=item.step, detail=item.detail) for item in args.path],
        commands=[
            CommandRecord(
                tool=item.tool,
                args=item.args,
                result_hash=item.result_hash,
                ok=item.ok,
            )
            for item in args.commands
        ],
        risks=list(args.risks),
        confidence=args.confidence,
        unresolved=list(args.unresolved),
        suggested_next=list(args.suggested_next),
        status=args.status,
    )
    _last_report.set(report)
    return SubmitExpertReportResult(
        ok=True,
        accepted=True,
        conclusion=report.conclusion,
    ).model_dump(mode="json")


def build_submit_report_definition(permission: str) -> ToolDefinition:
    """由各专家进程用本域权限码构造 submit_expert_report。"""
    return ToolDefinition(
        name=SUBMIT_REPORT,
        description="结束前必须调用一次，提交结构化专家报告。",
        parameters_model=SubmitExpertReportArgs,
        result_model=SubmitExpertReportResult,
        policy=ToolPolicy(
            effect=Effect.READ,
            risk=Risk.LOW,
            permission=permission,
            timeout_seconds=3.0,
            max_retries=0,
            idempotent=True,
        ),
        handler=_submit,  # type: ignore[arg-type]
    )
