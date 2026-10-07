from __future__ import annotations

from typing import Any, Optional

from app.core.agent.dispatch import pending_task_for_conversation, send_control
from app.core.agent.bus import load_meta
from app.core.agent.loop import resume_agent_after_decision, run_agent_loop
from app.core.audit import emit_gateway_audit
from app.core.config import get_settings


def chat(
    query: str,
    conversation_id: Optional[str] = None,
) -> dict[str, Any]:
    if not query or not query.strip():
        return {"error": {"code": 400, "message": "query 不能为空"}}
    if conversation_id:
        pending = pending_task_for_conversation(conversation_id)
        if pending:
            return {
                "query": query.strip(),
                "answer": "有待审批的专家操作，请先确认是否批准。",
                "steps": [],
                "humanCs": None,
                "conversationId": conversation_id,
                "approvalRequired": {
                    "requestId": pending,
                    "tool": "",
                    "args": {},
                    "summary": "专家任务等待审批",
                    "conversationId": conversation_id,
                },
            }
    data: dict[str, Any] | None = None
    try:
        data = run_agent_loop(query.strip(), conversation_id=conversation_id)
        return data
    finally:
        cid = None
        if isinstance(data, dict):
            cid = data.get("conversationId") or conversation_id
        else:
            cid = conversation_id
        emit_gateway_audit(
            path="/v1/agent/chat",
            method="POST",
            auth_ok=True,
            token=get_settings().access_token,
            conversation_id=cid,
            status_code=200,
            include_model_summary=True,
        )


def decide_approval(
    request_id: str,
    decision: str,
    conversation_id: Optional[str] = None,
) -> dict[str, Any]:
    """HITL：对 thread 上挂起的 interrupt 做 approve/reject（Command.resume）。

    requestId 约定为 conversationId（thread_id）。
    """
    rid = (request_id or "").strip()
    cid = (conversation_id or "").strip() or rid
    if not cid:
        return {"error": {"code": 400, "message": "conversationId 不能为空"}}

    task_id = pending_task_for_conversation(cid)
    if not task_id and load_meta(rid):
        task_id = rid
    if task_id:
        data = send_control(task_id, decision, cid)
        emit_gateway_audit(
            path=f"/v1/agent/approvals/{rid}/decide",
            method="POST",
            auth_ok=True,
            token=get_settings().access_token,
            conversation_id=cid,
            status_code=200 if "error" not in (data or {}) else int((data.get("error") or {}).get("code") or 500),
            include_model_summary=True,
        )
        return data

    if rid and cid and rid != cid:
        return {
            "error": {
                "code": 400,
                "message": "requestId 须与 conversationId 一致（均为 thread_id）",
            }
        }
    data: dict[str, Any] | None = None
    try:
        data = resume_agent_after_decision(cid, decision)
        return data
    finally:
        status_code = 200
        if isinstance(data, dict) and "error" in data:
            err = data.get("error") or {}
            status_code = int(err.get("code") or 500)
        emit_gateway_audit(
            path=f"/v1/agent/approvals/{rid}/decide",
            method="POST",
            auth_ok=True,
            token=get_settings().access_token,
            conversation_id=cid,
            status_code=status_code,
            include_model_summary=True,
        )
