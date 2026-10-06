"""会话注册表：只维护 conversationId 生命周期，对话内容在 LangGraph checkpoint。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

CONVERSATION_TTL_SECONDS = 2 * 60 * 60


@dataclass
class Conversation:
    conversation_id: str
    updated_at: float = field(default_factory=time.time)


_conversations: dict[str, Conversation] = {}


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


def ensure_conversation(conversation_id: Optional[str] = None) -> str:
    """返回可用 conversationId：有效则复用，客户端传入的 ID 也直接登记。"""
    _cleanup()
    cid = (conversation_id or "").strip()
    if cid:
        existing = _conversations.get(cid)
        if existing is not None and not _expired(existing):
            _touch(existing)
            return cid
        # 复用前端/checkpoint 已有 thread_id（进程重启后内存表可能为空）
        _conversations[cid] = Conversation(conversation_id=cid)
        return cid
    new_id = str(uuid.uuid4())
    _conversations[new_id] = Conversation(conversation_id=new_id)
    return new_id


def touch_conversation(conversation_id: str) -> None:
    conv = _conversations.get(conversation_id)
    if conv is None:
        _conversations[conversation_id] = Conversation(conversation_id=conversation_id)
    else:
        _touch(conv)


def clear_conversation(conversation_id: str) -> None:
    _conversations.pop(conversation_id, None)
    from app.core.agent.graph_runtime import drop_thread

    drop_thread(conversation_id)
