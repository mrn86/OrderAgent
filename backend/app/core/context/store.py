"""会话注册表：只维护 conversationId 生命周期，对话内容在 LangGraph checkpoint。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.core.redis_client import get_redis

CONVERSATION_TTL_SECONDS = 2 * 60 * 60
_CONV_KEY = "oa:conv:{cid}"


@dataclass
class Conversation:
    conversation_id: str
    updated_at: float = field(default_factory=time.time)


_conversations: dict[str, Conversation] = {}


def _redis():
    return get_redis(for_stream=True)


def _expired(conv: Conversation) -> bool:
    return time.time() - conv.updated_at > CONVERSATION_TTL_SECONDS


def _touch(conv: Conversation) -> None:
    conv.updated_at = time.time()


def _cleanup() -> None:
    stale = [cid for cid, c in list(_conversations.items()) if _expired(c)]
    if not stale:
        return
    from app.core.agent.graph_runtime import drop_thread

    for cid in stale:
        _conversations.pop(cid, None)
        drop_thread(cid)


def _touch_redis(cid: str) -> None:
    client = _redis()
    if client is None:
        return
    client.setex(_CONV_KEY.format(cid=cid), CONVERSATION_TTL_SECONDS, str(time.time()))


def ensure_conversation(conversation_id: Optional[str] = None) -> str:
    """返回可用 conversationId：有效则复用，客户端传入的 ID 也直接登记。"""
    client = _redis()
    cid = (conversation_id or "").strip()
    if client is not None:
        if cid:
            client.setex(_CONV_KEY.format(cid=cid), CONVERSATION_TTL_SECONDS, str(time.time()))
            return cid
        new_id = str(uuid.uuid4())
        client.setex(_CONV_KEY.format(cid=new_id), CONVERSATION_TTL_SECONDS, str(time.time()))
        return new_id

    _cleanup()
    if cid:
        existing = _conversations.get(cid)
        if existing is not None and not _expired(existing):
            _touch(existing)
            return cid
        _conversations[cid] = Conversation(conversation_id=cid)
        return cid
    new_id = str(uuid.uuid4())
    _conversations[new_id] = Conversation(conversation_id=new_id)
    return new_id


def touch_conversation(conversation_id: str) -> None:
    if _redis() is not None:
        _touch_redis(conversation_id)
        return
    conv = _conversations.get(conversation_id)
    if conv is None:
        _conversations[conversation_id] = Conversation(conversation_id=conversation_id)
    else:
        _touch(conv)


def clear_conversation(conversation_id: str) -> None:
    client = _redis()
    if client is not None:
        client.delete(_CONV_KEY.format(cid=conversation_id))
    _conversations.pop(conversation_id, None)
    from app.core.agent.graph_runtime import drop_thread

    drop_thread(conversation_id)
