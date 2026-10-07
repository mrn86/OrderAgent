"""路由对用户可见答复的输出 schema。

ExpertReport / verified / confidence 仍仅用于总线与复核；
前端与 SSE 只允许消费本 schema 的 message 字段。
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


_CONFIDENCE_LINE = re.compile(r"置信度|confidence", re.I)
_JSON_OBJECT = re.compile(r"\{[\s\S]*\}")


class RouterUserReply(BaseModel):
    """模型/循环最终对用户输出的唯一合法结构。"""

    model_config = ConfigDict(extra="ignore")  # 丢弃 confidence / verified 等额外键

    message: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="给用户的 Markdown 业务说明（订单/物流/发票等），不含内部协议字段",
    )

    @field_validator("message", mode="before")
    @classmethod
    def _normalize_message(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("message 不能为空")
        lines = [ln for ln in text.splitlines() if not _CONFIDENCE_LINE.search(ln)]
        cleaned = "\n".join(lines).strip()
        if not cleaned:
            raise ValueError("message 在去除内部字段后为空")
        return cleaned


def _parse_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    match = _JSON_OBJECT.search(raw)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _message_from_mapping(data: dict[str, Any]) -> str | None:
    for key in ("message", "answer", "conclusion", "userMessage", "content"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    report = data.get("report")
    if isinstance(report, dict):
        c = report.get("conclusion")
        if isinstance(c, str) and c.strip():
            return c.strip()
    return None


def coerce_user_reply(
    raw: str,
    *,
    fallbacks: list[str] | None = None,
) -> RouterUserReply:
    """将模型自由文本 / JSON 强制收敛为 RouterUserReply（output schema 门禁）。"""
    text = (raw or "").strip()
    candidates: list[str] = []

    parsed = _parse_json_object(text)
    if parsed is not None:
        # schema：只取白名单业务字段；extra=ignore 丢掉 confidence 等
        msg = _message_from_mapping(parsed)
        if msg:
            candidates.append(msg)
        # 整段若是协议 dump 且抽不到 message，不把原文当 message
        protocol_keys = {"verified", "evidence", "commands", "result_hash", "taskId", "report"}
        if not msg and not (protocol_keys & set(parsed)):
            # 普通 JSON 无已知键时不原样塞入
            pass
    elif text:
        candidates.append(text)

    for fb in fallbacks or []:
        if isinstance(fb, str) and fb.strip():
            candidates.append(fb.strip())

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            return RouterUserReply(message=candidate)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    if last_error is not None:
        # 兜底：去掉置信度行后再试一次硬包装
        scrubbed = "\n".join(
            ln for ln in (text or "暂无业务结果可展示。").splitlines() if not _CONFIDENCE_LINE.search(ln)
        ).strip() or "暂无业务结果可展示。"
        return RouterUserReply(message=scrubbed)

    return RouterUserReply(message="暂无业务结果可展示。")


def user_visible_message(raw: str, *, fallbacks: list[str] | None = None) -> str:
    """SSE / 同步接口最终 answer：仅 schema.message。"""
    return coerce_user_reply(raw, fallbacks=fallbacks).message
