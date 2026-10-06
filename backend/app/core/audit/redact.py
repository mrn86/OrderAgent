"""审计落盘前脱敏：敏感字段名 + 文本中的 PII。"""

from __future__ import annotations

import re
from typing import Any, Mapping

_SENSITIVE_KEY = re.compile(
    r"token|secret|password|authorization|api_?key|credential|cookie|session|private_?key|access_?key",
    re.I,
)

_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_URL = re.compile(r"https?://[^\s<>\"']+", re.I)
_CN_MOBILE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_CN_ID = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total = 0
    alt = False
    for ch in reversed(digits):
        n = ord(ch) - 48
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        alt = not alt
    return total % 10 == 0


def _redact_cards(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            return "[REDACTED_CREDIT_CARD]"
        return match.group(0)

    return _CARD_CANDIDATE.sub(repl, text)


def redact_text(text: str) -> str:
    out = _EMAIL.sub("[REDACTED_EMAIL]", text)
    out = _URL.sub("[REDACTED_URL]", out)
    out = _CN_ID.sub("[REDACTED_CN_ID]", out)
    out = _CN_MOBILE.sub("[REDACTED_CN_MOBILE]", out)
    return _redact_cards(out)


def redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if _SENSITIVE_KEY.search(name):
                out[name] = "***"
            else:
                out[name] = redact_value(item)
        return out
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
