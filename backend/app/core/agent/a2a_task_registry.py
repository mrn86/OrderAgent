"""专家进程内 HITL 挂起任务（A2A 完成后等待 /v1/a2a/resume）。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.agent.protocol import DispatchEnvelope
from app.core.agent.tools.permissions import ExecutionContext


@dataclass
class ParkedExpertTask:
    envelope: DispatchEnvelope
    thread_id: str
    execution_ctx: ExecutionContext
    started: float
    approval: dict[str, Any] = field(default_factory=dict)


_lock = threading.Lock()
_parked: dict[str, ParkedExpertTask] = {}


def park_task(task_id: str, parked: ParkedExpertTask) -> None:
    with _lock:
        _parked[task_id] = parked


def take_parked(task_id: str) -> ParkedExpertTask | None:
    with _lock:
        return _parked.pop(task_id, None)


def peek_parked(task_id: str) -> ParkedExpertTask | None:
    with _lock:
        return _parked.get(task_id)


def parked_age_seconds(task_id: str) -> float | None:
    with _lock:
        item = _parked.get(task_id)
        if item is None:
            return None
        return time.perf_counter() - item.started
