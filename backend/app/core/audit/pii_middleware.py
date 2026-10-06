"""组装挂到 create_agent 的 LangChain PIIMiddleware。"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import PIIMiddleware


def build_pii_middlewares() -> list[Any]:
    common = dict(
        strategy="redact",
        apply_to_input=True,
        apply_to_output=True,
        apply_to_tool_results=True,
    )
    return [
        PIIMiddleware("email", **common),
        PIIMiddleware("credit_card", **common),
        PIIMiddleware("url", **common),
        PIIMiddleware("cn_mobile", detector=r"1[3-9]\d{9}", **common),
        PIIMiddleware("cn_id", detector=r"\d{17}[\dXx]", **common),
    ]
