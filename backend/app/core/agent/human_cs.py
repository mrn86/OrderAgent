"""人工客服兜底。

职责：
1. 主 Agent 通过 escalate_to_human_cs 主动转人工；
2. 结束后若未调业务工具且答复像无法处理，强制注入转人工结果；
3. 统一构造 humanCs 载荷（含客服链接）。
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.core.agent.domain_registry import (
    business_tools,
    domain_markers,
    human_cs_scope_blurb,
)
from app.core.config import get_settings

# 模型答复中「无法处理」类表述，用于结束后强制兜底
CANNOT_ANSWER_PATTERNS = [
    r"无法(查询|处理|回答|解决|帮助)",
    r"不能(查询|处理|回答|解决|帮助)",
    r"超出(我的)?(能力|范围)",
    r"暂不支持",
    r"没有相关(工具|能力|权限)",
    r"建议联系人工",
    r"转人工",
]


def _ensure_domain() -> None:
    from app.domains.ecommerce import ensure_ecommerce_domain

    ensure_ecommerce_domain()


class _BusinessToolsProxy:
    """保持 `tool in BUSINESS_TOOLS` 写法，内容来自 domain registry。"""

    def __contains__(self, item: object) -> bool:
        _ensure_domain()
        return item in business_tools()

    def __iter__(self):
        _ensure_domain()
        return iter(business_tools())

    def __len__(self) -> int:
        _ensure_domain()
        return len(business_tools())


BUSINESS_TOOLS = _BusinessToolsProxy()


def build_human_cs_payload(reason: str = "当前问题无法自动处理") -> dict[str, Any]:
    """构造前端可识别的人工客服载荷。"""
    settings = get_settings()
    url = settings.human_cs_url
    return {
        "needHuman": True,
        "reason": reason,
        "csName": "人工客服",
        "csUrl": url,
        "guide": f"如需进一步帮助，请联系人工客服：{url}",
    }


def has_escalate_step(steps: list[dict[str, Any]]) -> bool:
    """工具轨迹中是否已包含转人工步骤。"""
    return any(step.get("tool") == "escalate_to_human_cs" for step in steps or [])


def has_business_tool_step(steps: list[dict[str, Any]]) -> bool:
    """是否调用过任一业务查询工具。"""
    _ensure_domain()
    tools = business_tools()
    return any(step.get("tool") in tools for step in steps or [])


def answer_looks_unable(answer: str) -> bool:
    """模型答复是否像「答不上来」。空答复也视为无法回答。"""
    text = (answer or "").strip()
    if not text:
        return True
    return any(re.search(p, text) for p in CANNOT_ANSWER_PATTERNS)


def _query_looks_in_domain(query: str) -> bool:
    _ensure_domain()
    text = query or ""
    return any(marker in text for marker in domain_markers())


def should_force_human_cs(
    query: str,
    steps: list[dict[str, Any]],
    answer: str,
) -> Optional[str]:
    """是否需要强制转人工（主 Agent 未主动 escalate 时的兜底）。

    Returns:
        强制原因字符串；若不需要强制则返回 None。
    """
    if has_escalate_step(steps):
        return None

    # 业务范围内：不因模型空答/推诿而强制转人工（应由主 Agent 追问或调工具）
    if _query_looks_in_domain(query):
        return None

    # 未做业务查询且答复像无法处理 -> 强制兜底
    if not has_business_tool_step(steps) and answer_looks_unable(answer):
        return "当前问题无法由智能助手可靠处理"

    return None


def human_cs_fallback_answer(reason: str) -> str:
    """生成带 Markdown 客服链接的中文兜底回复。"""
    _ensure_domain()
    payload = build_human_cs_payload(reason)
    scope = human_cs_scope_blurb()
    return (
        f"抱歉，我主要处理{scope}，"
        f"{reason}。建议您联系人工客服获取帮助：[{payload['csName']}]({payload['csUrl']})"
    )


# 兼容旧名
out_of_scope_answer = human_cs_fallback_answer
