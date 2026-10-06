"""SSE 会话：事件经 Redis Stream 跨实例可读（需 Redis 5+）。

模型：
- POST 建会话的实例负责跑 Agent（生产者）并 XADD
- 任意实例的 EventSource GET 用 XREAD（按 Last-Event-ID）消费
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from app.core.agent.loop import stream_agent_loop
from app.core.audit import (
    emit_gateway_audit,
    ensure_audit_request_id,
    get_audit_request_id,
    get_trace_id,
    set_audit_ids,
)
from app.core.context import ensure_conversation
from app.core.redis_client import get_async_redis

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 30 * 60
RECONNECT_RETRY_MS = 2000
XREAD_BLOCK_MS = 2000

META_KEY = "oa:sse:meta:{sid}"
STREAM_KEY = "oa:sse:stream:{sid}"


class RedisStreamUnavailable(RuntimeError):
    """Redis 不可用或不支持 Stream（需升级到 Redis 5+）。"""


@dataclass
class StreamSession:
    session_id: str
    conversation_id: str
    query: str = ""
    audit_request_id: str = ""
    trace_id: str = ""


class RedisStreamBackend:
    def __init__(self, client: Any) -> None:
        self._r = client

    def _meta(self, sid: str) -> str:
        return META_KEY.format(sid=sid)

    def _stream(self, sid: str) -> str:
        return STREAM_KEY.format(sid=sid)

    async def _load_meta(self, session_id: str) -> Optional[dict[str, Any]]:
        raw = await self._r.get(self._meta(session_id))
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None

    async def _save_meta(self, session_id: str, data: dict[str, Any]) -> None:
        await self._r.setex(
            self._meta(session_id),
            SESSION_TTL_SECONDS,
            json.dumps(data, ensure_ascii=False),
        )

    async def create(self, session: StreamSession) -> None:
        await self._save_meta(
            session.session_id,
            {
                "conversation_id": session.conversation_id,
                "query": session.query,
                "created_at": time.time(),
                "done": False,
            },
        )

    async def exists(self, session_id: str) -> bool:
        return bool(await self._r.exists(self._meta(session_id)))

    async def publish(self, session_id: str, payload: dict[str, Any]) -> str:
        stream = self._stream(session_id)
        msg_id = await self._r.xadd(
            stream,
            {"payload": json.dumps(payload, ensure_ascii=False)},
        )
        await self._r.expire(stream, SESSION_TTL_SECONDS)
        meta = await self._load_meta(session_id) or {}
        if payload.get("type") in {"done", "error"}:
            meta["done"] = True
        await self._save_meta(session_id, meta)
        return str(msg_id)

    async def is_done(self, session_id: str) -> bool:
        meta = await self._load_meta(session_id)
        return bool(meta and meta.get("done"))

    async def read_after(
        self,
        session_id: str,
        last_id: str,
        *,
        block_ms: int,
    ) -> list[tuple[str, dict[str, Any]]]:
        stream = self._stream(session_id)
        start = last_id if last_id else "0-0"
        rows = await self._r.xread({stream: start}, block=block_ms, count=100)
        out: list[tuple[str, dict[str, Any]]] = []
        if not rows:
            return out
        for _name, messages in rows:
            for msg_id, fields in messages:
                raw = fields.get("payload") or "{}"
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                out.append((str(msg_id), payload))
        return out


_backend: Optional[RedisStreamBackend] = None
_backend_lock = asyncio.Lock()
_local_tasks: dict[str, asyncio.Task] = {}


async def _require_stream_support(client: Any) -> None:
    probe = "oa:sse:probe"
    try:
        await client.xadd(probe, {"p": "1"})
        await client.delete(probe)
    except Exception as exc:
        try:
            await client.delete(probe)
        except Exception:
            pass
        raise RedisStreamUnavailable(
            "当前 Redis 不支持 Stream（XADD）。请升级到 Redis 5.0 及以上。"
        ) from exc


async def _get_backend() -> RedisStreamBackend:
    global _backend
    if _backend is not None:
        return _backend
    async with _backend_lock:
        if _backend is not None:
            return _backend
        client = await get_async_redis(for_stream=True)
        if client is None:
            raise RedisStreamUnavailable(
                "无法连接 Redis（SSE 依赖 Redis Stream）。请检查 REDIS_URL，"
                "并确保 Redis 版本 >= 5.0。"
            )
        await _require_stream_support(client)
        _backend = RedisStreamBackend(client)
        logger.info("SSE stream backend: Redis Stream")
        return _backend


async def _publish(
    backend: RedisStreamBackend,
    session: StreamSession,
    payload: dict[str, Any],
) -> str:
    if "conversationId" not in payload:
        payload = {**payload, "conversationId": session.conversation_id}
    return await backend.publish(session.session_id, payload)


async def _run_session(
    backend: RedisStreamBackend,
    session: StreamSession,
) -> None:
    if session.audit_request_id:
        set_audit_ids(session.audit_request_id, session.trace_id or session.audit_request_id)
    try:
        async for event in stream_agent_loop(
            session.query,
            conversation_id=session.conversation_id,
        ):
            await _publish(backend, session, event)
        if not await backend.is_done(session.session_id):
            await _publish(
                backend,
                session,
                {
                    "type": "done",
                    "query": session.query,
                    "answer": "",
                    "steps": [],
                    "humanCs": None,
                    "conversationId": session.conversation_id,
                },
            )
    except asyncio.CancelledError:
        await _publish(backend, session, {"type": "error", "message": "会话已取消"})
        raise
    except Exception as exc:  # noqa: BLE001
        if not await backend.is_done(session.session_id):
            await _publish(backend, session, {"type": "error", "message": str(exc)})
    finally:
        from app.core.config import get_settings

        emit_gateway_audit(
            path="/v1/agent/chat/stream/sessions",
            method="POST",
            auth_ok=True,
            token=get_settings().access_token,
            conversation_id=session.conversation_id,
            status_code=200,
            include_model_summary=True,
        )
        _local_tasks.pop(session.session_id, None)


async def create_stream_session(
    query: str,
    conversation_id: Optional[str] = None,
) -> StreamSession:
    backend = await _get_backend()
    cid = ensure_conversation(conversation_id)
    ensure_audit_request_id()
    session = StreamSession(
        session_id=str(uuid.uuid4()),
        conversation_id=cid,
        query=query,
        audit_request_id=get_audit_request_id() or "",
        trace_id=get_trace_id() or "",
    )
    await backend.create(session)
    task = asyncio.create_task(_run_session(backend, session))
    _local_tasks[session.session_id] = task
    return session


async def get_stream_session(session_id: str) -> Optional[StreamSession]:
    backend = await _get_backend()
    if not await backend.exists(session_id):
        return None
    return StreamSession(session_id=session_id, conversation_id="")


def format_sse(event_id: str | int, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    event_name = "complete" if payload.get("type") in {"done", "error"} else "message"
    return f"id: {event_id}\nevent: {event_name}\ndata: {data}\n\n"


def _normalize_last_id(last_event_id: str | int | None) -> str:
    if last_event_id is None or last_event_id == "":
        return "0-0"
    text = str(last_event_id).strip()
    if not text:
        return "0-0"
    if text.isdigit():
        return f"{text}-0" if text != "0" else "0-0"
    return text


async def iter_session_sse(
    session: StreamSession | str,
    last_event_id: str | int = "0-0",
) -> AsyncIterator[str]:
    backend = await _get_backend()
    session_id = session.session_id if isinstance(session, StreamSession) else session
    cursor = _normalize_last_id(last_event_id)
    yield f"retry: {RECONNECT_RETRY_MS}\n\n"

    while True:
        if not await backend.exists(session_id):
            yield format_sse(
                "1-0",
                {"type": "error", "message": "会话不存在或已过期"},
            )
            return

        pending = await backend.read_after(
            session_id,
            cursor,
            block_ms=XREAD_BLOCK_MS,
        )
        if pending:
            for event_id, payload in pending:
                cursor = event_id
                yield format_sse(event_id, payload)
                if payload.get("type") in {"done", "error"}:
                    return
            continue

        if await backend.is_done(session_id):
            tail = await backend.read_after(session_id, cursor, block_ms=0)
            for event_id, payload in tail:
                cursor = event_id
                yield format_sse(event_id, payload)
                if payload.get("type") in {"done", "error"}:
                    return
            return
