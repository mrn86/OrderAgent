from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.response import fail, ok
import app.gateway.service as agent_service
from app.gateway.rate_limit import check_rate_limit
from app.gateway.stream_sessions import (
    RedisStreamUnavailable,
    create_stream_session,
    format_sse,
    get_stream_session,
    iter_session_sse,
)

# 鉴权 + HTTP 限流
router = APIRouter(dependencies=[Depends(check_rate_limit)])
sse_router = APIRouter()


class AgentChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    # 后端维护的多轮会话 ID；首次可空，服务端会新建并回传
    conversationId: Optional[str] = Field(default=None, min_length=8, max_length=64)


class ApprovalDecideRequest(BaseModel):
    decision: Literal["approve", "reject"]
    conversationId: Optional[str] = Field(default=None, min_length=8, max_length=64)


def _sse_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }


@router.post("/agent/chat")
def agent_chat(body: AgentChatRequest):
    data = agent_service.chat(body.query, conversation_id=body.conversationId)
    if "error" in data:
        err = data["error"]
        return fail(err["code"], err["message"])
    return ok(data)


@router.post("/agent/chat/stream/sessions")
async def create_agent_stream_session(body: AgentChatRequest):
    try:
        session = await create_stream_session(
            body.query,
            conversation_id=body.conversationId,
        )
    except RedisStreamUnavailable as exc:
        return fail(503, str(exc))
    return ok(
        {
            "sessionId": session.session_id,
            "conversationId": session.conversation_id,
        }
    )


@router.post("/agent/approvals/{request_id}/decide")
def decide_approval(request_id: str, body: ApprovalDecideRequest):
    """HITL：批准/拒绝 thread 上挂起的高风险工具（request_id = conversationId）。"""
    data = agent_service.decide_approval(
        request_id,
        body.decision,
        conversation_id=body.conversationId,
    )
    if "error" in data:
        err = data["error"]
        return fail(err["code"], err["message"])
    return ok(data)


@sse_router.get("/agent/chat/stream")
async def agent_chat_stream_eventsource(
    sessionId: str = Query(..., min_length=8),
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
):
    """EventSource 订阅（浏览器无法带 Authorization，鉴权在建会话 POST）。

    Last-Event-ID 为 Redis Stream ID（如 1712345678901-0）；跨实例可回放。
    """
    cursor = (last_event_id or "").strip() or "0-0"
    try:
        session = await get_stream_session(sessionId)
    except RedisStreamUnavailable as exc:

        async def _redis_err():
            yield "retry: 2000\n\n"
            yield format_sse("1-0", {"type": "error", "message": str(exc)})

        return StreamingResponse(
            _redis_err(),
            media_type="text/event-stream",
            headers=_sse_headers(),
        )

    if session is None:

        async def _missing():
            yield "retry: 2000\n\n"
            yield format_sse("1-0", {"type": "error", "message": "会话不存在或已过期"})

        return StreamingResponse(
            _missing(),
            media_type="text/event-stream",
            headers=_sse_headers(),
        )

    return StreamingResponse(
        iter_session_sse(session, last_event_id=cursor),
        media_type="text/event-stream",
        headers=_sse_headers(),
    )
