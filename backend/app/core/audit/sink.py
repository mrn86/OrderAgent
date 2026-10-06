"""审计输出：默认一行 JSON 日志。"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping, Protocol

from app.core.audit.redact import redact_value

logger = logging.getLogger("app.audit")


class AuditSink(Protocol):
    def write(self, record: Mapping[str, Any]) -> None: ...


class JsonLoggerAuditSink:
    def write(self, record: Mapping[str, Any]) -> None:
        logger.info("%s", json.dumps(dict(record), ensure_ascii=False, default=str))


_default_sink: AuditSink = JsonLoggerAuditSink()


def get_audit_sink() -> AuditSink:
    return _default_sink


def emit_record(record: Mapping[str, Any]) -> None:
    try:
        get_audit_sink().write(redact_value(dict(record)))
    except Exception:  # noqa: BLE001
        logger.warning("audit emit failed", exc_info=True)
