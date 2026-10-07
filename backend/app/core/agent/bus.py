"""任务总线：dispatch / events / control。Redis Stream 优先，内存实现供单测。"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Protocol

from app.core.config import get_settings
from app.core.redis_client import get_async_redis, get_redis

logger = logging.getLogger(__name__)

TTL_DEFAULT = 1800
MAXLEN_DEFAULT = 10000

DISPATCH_STREAM = "oa:dispatch:{expert}"
EVENTS_STREAM = "oa:task:{task_id}:events"
CONTROL_STREAM = "oa:task:{task_id}:control"
META_KEY = "oa:task:{task_id}:meta"
HITL_KEY = "oa:conv:{cid}:hitl"
GROUP_ORDER = "order-workers"
GROUP_LOGISTICS = "logistics-workers"
GROUP_INVOICE = "invoice-workers"


def dispatch_stream(expert: str) -> str:
    return DISPATCH_STREAM.format(expert=expert)


def events_stream(task_id: str) -> str:
    return EVENTS_STREAM.format(task_id=task_id)


def control_stream(task_id: str) -> str:
    return CONTROL_STREAM.format(task_id=task_id)


def worker_group(expert: str) -> str:
    if expert == "order":
        return GROUP_ORDER
    if expert == "logistics":
        return GROUP_LOGISTICS
    return GROUP_INVOICE


class TaskBus(Protocol):
    def xadd(self, stream: str, fields: dict[str, str], *, maxlen: int | None = None) -> str: ...
    def xread(
        self, stream: str, last_id: str, *, block_ms: int, count: int
    ) -> list[tuple[str, dict[str, str]]]: ...
    def ensure_group(self, stream: str, group: str) -> None: ...
    def xreadgroup(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        block_ms: int,
        count: int,
    ) -> list[tuple[str, dict[str, str]]]: ...
    def xack(self, stream: str, group: str, msg_id: str) -> None: ...
    def setex(self, key: str, ttl: int, value: str) -> None: ...
    def get(self, key: str) -> str | None: ...
    def delete(self, key: str) -> None: ...


class MemoryTaskBus:
    """进程内 Stream 模拟（单测 / Redis 不可用时）。不能跨进程。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seq = 0
        self._streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self._acked: dict[tuple[str, str], set[str]] = {}
        self._pending: dict[tuple[str, str], dict[str, str]] = {}
        self._kv: dict[str, tuple[float, str]] = {}
        self._cv = threading.Condition(self._lock)

    def _now_id(self) -> str:
        self._seq += 1
        return f"{int(time.time() * 1000)}-{self._seq}"

    def _purge_kv(self) -> None:
        now = time.time()
        dead = [k for k, (exp, _) in self._kv.items() if exp < now]
        for k in dead:
            self._kv.pop(k, None)

    def xadd(self, stream: str, fields: dict[str, str], *, maxlen: int | None = None) -> str:
        with self._cv:
            msg_id = self._now_id()
            bucket = self._streams.setdefault(stream, [])
            bucket.append((msg_id, dict(fields)))
            if maxlen and len(bucket) > maxlen:
                self._streams[stream] = bucket[-maxlen:]
            self._cv.notify_all()
            return msg_id

    def xread(
        self, stream: str, last_id: str, *, block_ms: int, count: int
    ) -> list[tuple[str, dict[str, str]]]:
        deadline = time.time() + max(0, block_ms) / 1000.0
        with self._cv:
            while True:
                out: list[tuple[str, dict[str, str]]] = []
                for msg_id, fields in self._streams.get(stream, []):
                    if last_id == "0-0" or _id_gt(msg_id, last_id):
                        out.append((msg_id, dict(fields)))
                        if len(out) >= count:
                            break
                if out or block_ms <= 0 or time.time() >= deadline:
                    return out
                remaining = deadline - time.time()
                if remaining <= 0:
                    return []
                self._cv.wait(timeout=remaining)

    def ensure_group(self, stream: str, group: str) -> None:
        with self._lock:
            self._streams.setdefault(stream, [])
            self._acked.setdefault((stream, group), set())
            self._pending.setdefault((stream, group), {})

    def xreadgroup(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        block_ms: int,
        count: int,
    ) -> list[tuple[str, dict[str, str]]]:
        self.ensure_group(stream, group)
        deadline = time.time() + max(0, block_ms) / 1000.0
        with self._cv:
            while True:
                key = (stream, group)
                acked = self._acked[key]
                pending = self._pending[key]
                by_id = {msg_id: fields for msg_id, fields in self._streams.get(stream, [])}
                out: list[tuple[str, dict[str, str]]] = []
                for msg_id, owner in list(pending.items()):
                    if owner == consumer and msg_id not in acked and msg_id in by_id:
                        out.append((msg_id, dict(by_id[msg_id])))
                        if len(out) >= count:
                            break
                if len(out) < count:
                    for msg_id, fields in self._streams.get(stream, []):
                        if msg_id in acked or msg_id in pending:
                            continue
                        pending[msg_id] = consumer
                        out.append((msg_id, dict(fields)))
                        if len(out) >= count:
                            break
                if out or block_ms <= 0 or time.time() >= deadline:
                    return out
                remaining = deadline - time.time()
                if remaining <= 0:
                    return []
                self._cv.wait(timeout=remaining)

    def xack(self, stream: str, group: str, msg_id: str) -> None:
        with self._lock:
            self._acked.setdefault((stream, group), set()).add(msg_id)
            self._pending.setdefault((stream, group), {}).pop(msg_id, None)

    def setex(self, key: str, ttl: int, value: str) -> None:
        with self._lock:
            self._kv[key] = (time.time() + max(1, ttl), value)

    def get(self, key: str) -> str | None:
        with self._lock:
            self._purge_kv()
            item = self._kv.get(key)
            if not item:
                return None
            return item[1]

    def delete(self, key: str) -> None:
        with self._lock:
            self._kv.pop(key, None)


def _id_gt(left: str, right: str) -> bool:
    def parts(value: str) -> tuple[int, int]:
        bits = (value or "0-0").split("-")
        try:
            return int(bits[0]), int(bits[1] if len(bits) > 1 else 0)
        except ValueError:
            return 0, 0

    return parts(left) > parts(right)


class RedisTaskBus:
    def __init__(self, client: Any) -> None:
        self._r = client
        settings = get_settings()
        self._maxlen = max(100, int(settings.dispatch_stream_maxlen))

    def xadd(self, stream: str, fields: dict[str, str], *, maxlen: int | None = None) -> str:
        cap = maxlen if maxlen is not None else self._maxlen
        msg_id = self._r.xadd(stream, fields, maxlen=cap, approximate=True)
        ttl = int(get_settings().task_ttl_seconds)
        self._r.expire(stream, ttl)
        return str(msg_id)

    def xread(
        self, stream: str, last_id: str, *, block_ms: int, count: int
    ) -> list[tuple[str, dict[str, str]]]:
        rows = self._r.xread({stream: last_id or "0-0"}, block=block_ms, count=count)
        out: list[tuple[str, dict[str, str]]] = []
        if not rows:
            return out
        for _name, messages in rows:
            for msg_id, fields in messages:
                out.append((str(msg_id), {str(k): str(v) for k, v in fields.items()}))
        return out

    def ensure_group(self, stream: str, group: str) -> None:
        try:
            self._r.xgroup_create(stream, group, id="0-0", mkstream=True)
        except Exception as exc:  # noqa: BLE001
            if "BUSYGROUP" not in str(exc):
                logger.debug("xgroup_create %s %s: %s", stream, group, exc)

    def xreadgroup(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        block_ms: int,
        count: int,
    ) -> list[tuple[str, dict[str, str]]]:
        self.ensure_group(stream, group)
        rows = self._r.xreadgroup(
            group,
            consumer,
            {stream: ">"},
            count=count,
            block=block_ms,
        )
        out: list[tuple[str, dict[str, str]]] = []
        if not rows:
            return out
        for _name, messages in rows:
            for msg_id, fields in messages:
                out.append((str(msg_id), {str(k): str(v) for k, v in fields.items()}))
        return out

    def xack(self, stream: str, group: str, msg_id: str) -> None:
        self._r.xack(stream, group, msg_id)

    def xautoclaim_idle(self, stream: str, group: str, consumer: str, min_idle_ms: int) -> None:
        try:
            self._r.xautoclaim(stream, group, consumer, min_idle_ms, "0-0", count=20)
        except Exception:
            logger.debug("xautoclaim skipped", exc_info=True)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self._r.setex(key, ttl, value)

    def get(self, key: str) -> str | None:
        raw = self._r.get(key)
        if raw is None:
            return None
        return raw if isinstance(raw, str) else raw.decode("utf-8")

    def delete(self, key: str) -> None:
        self._r.delete(key)


_bus: TaskBus | None = None
_bus_lock = threading.Lock()
_force_memory = False


def use_memory_bus(bus: MemoryTaskBus | None = None) -> MemoryTaskBus:
    """测试注入：强制内存总线。"""
    global _bus, _force_memory
    mem = bus or MemoryTaskBus()
    with _bus_lock:
        _bus = mem
        _force_memory = True
    return mem


def reset_task_bus() -> None:
    global _bus, _force_memory
    with _bus_lock:
        _bus = None
        _force_memory = False


def get_task_bus() -> TaskBus:
    global _bus
    if _bus is not None:
        return _bus
    with _bus_lock:
        if _bus is not None:
            return _bus
        if _force_memory:
            _bus = MemoryTaskBus()
            return _bus
        client = get_redis(for_stream=True)
        if client is not None:
            _bus = RedisTaskBus(client)
            logger.info("task bus: Redis Stream")
            return _bus
        logger.warning("task bus: Redis 不可用，回退进程内 MemoryTaskBus（不能跨进程）")
        _bus = MemoryTaskBus()
        return _bus


def publish_json(stream: str, payload: dict[str, Any]) -> str:
    return get_task_bus().xadd(stream, {"payload": json.dumps(payload, ensure_ascii=False)})


def read_payloads(
    stream: str, last_id: str, *, block_ms: int, count: int = 50
) -> list[tuple[str, dict[str, Any]]]:
    rows = get_task_bus().xread(stream, last_id, block_ms=block_ms, count=count)
    out: list[tuple[str, dict[str, Any]]] = []
    for msg_id, fields in rows:
        raw = fields.get("payload") or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            out.append((msg_id, data))
    return out


def save_meta(task_id: str, data: dict[str, Any]) -> None:
    ttl = int(get_settings().task_ttl_seconds)
    get_task_bus().setex(META_KEY.format(task_id=task_id), ttl, json.dumps(data, ensure_ascii=False))


def load_meta(task_id: str) -> dict[str, Any] | None:
    raw = get_task_bus().get(META_KEY.format(task_id=task_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def set_pending_hitl(conversation_id: str, task_id: str) -> None:
    ttl = int(get_settings().task_ttl_seconds)
    get_task_bus().setex(HITL_KEY.format(cid=conversation_id), ttl, task_id)


def get_pending_hitl(conversation_id: str) -> str | None:
    return get_task_bus().get(HITL_KEY.format(cid=conversation_id))


def clear_pending_hitl(conversation_id: str) -> None:
    get_task_bus().delete(HITL_KEY.format(cid=conversation_id))


async def ping_stream_redis() -> bool:
    client = await get_async_redis(for_stream=True)
    return client is not None
