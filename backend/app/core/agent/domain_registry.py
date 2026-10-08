"""可插拔业务域注册表：平台不写死专家名 / 证据源 / 列表结论 / 送模视图。"""

from __future__ import annotations

from typing import Any, Callable

EvidenceFetcher = Callable[[str], Any | None]
ListConclusionFormatter = Callable[[list[dict[str, Any]] | None], str | None]
PreferReplyHook = Callable[[str, list[str] | None], str]
ResultView = Callable[[dict[str, Any]], dict[str, Any]]

_evidence_fetchers: dict[str, EvidenceFetcher] = {}
_list_tools: set[str] = set()
_list_evidence_sources: set[str] = set()
_business_tools: set[str] = set()
_domain_markers: list[str] = []
_list_conclusion_formatters: list[ListConclusionFormatter] = []
_prefer_reply_hooks: list[PreferReplyHook] = []
_result_views: dict[str, ResultView] = {}
_supplement_hints: list[str] = []
_human_cs_scope_blurb: str = "相关业务问题"
_registered_packs: set[str] = set()


def reset_domain_registry() -> None:
    """单测用：清空全部注册项。"""
    _evidence_fetchers.clear()
    _list_tools.clear()
    _list_evidence_sources.clear()
    _business_tools.clear()
    _domain_markers.clear()
    _list_conclusion_formatters.clear()
    _prefer_reply_hooks.clear()
    _result_views.clear()
    _supplement_hints.clear()
    _registered_packs.clear()
    global _human_cs_scope_blurb
    _human_cs_scope_blurb = "相关业务问题"


def mark_pack_registered(pack_id: str) -> bool:
    """若尚未注册过该 pack 则标记并返回 True。"""
    if pack_id in _registered_packs:
        return False
    _registered_packs.add(pack_id)
    return True


def register_evidence_fetcher(source: str, fetcher: EvidenceFetcher) -> None:
    key = (source or "").strip().lower()
    if key:
        _evidence_fetchers[key] = fetcher


def register_list_tools(tools: set[str] | frozenset[str] | list[str]) -> None:
    _list_tools.update(str(t) for t in tools if t)


def register_list_evidence_sources(sources: set[str] | frozenset[str] | list[str]) -> None:
    _list_evidence_sources.update(str(s).strip().lower() for s in sources if s)


def register_business_tools(tools: set[str] | frozenset[str] | list[str]) -> None:
    _business_tools.update(str(t) for t in tools if t)


def register_domain_markers(markers: list[str] | tuple[str, ...]) -> None:
    for marker in markers:
        text = str(marker).strip()
        if text and text not in _domain_markers:
            _domain_markers.append(text)


def register_list_conclusion_formatter(formatter: ListConclusionFormatter) -> None:
    if formatter not in _list_conclusion_formatters:
        _list_conclusion_formatters.append(formatter)


def register_prefer_reply_hook(hook: PreferReplyHook) -> None:
    if hook not in _prefer_reply_hooks:
        _prefer_reply_hooks.append(hook)


def register_result_view(tool_name: str, view: ResultView) -> None:
    name = (tool_name or "").strip()
    if name:
        _result_views[name] = view


def register_supplement_hint(hint: str) -> None:
    text = (hint or "").strip()
    if text and text not in _supplement_hints:
        _supplement_hints.append(text)


def set_human_cs_scope_blurb(blurb: str) -> None:
    global _human_cs_scope_blurb
    text = (blurb or "").strip()
    if text:
        _human_cs_scope_blurb = text


def fetch_live_record(source: str, record_id: str) -> Any | None:
    rid = (record_id or "").strip()
    if not rid:
        return None
    src = (source or "").strip().lower()
    fetcher = _evidence_fetchers.get(src)
    if fetcher is None:
        return None
    return fetcher(rid)


def list_tools() -> frozenset[str]:
    return frozenset(_list_tools)


def is_list_evidence_source(source: str) -> bool:
    return (source or "").strip().lower() in _list_evidence_sources


def business_tools() -> frozenset[str]:
    return frozenset(_business_tools)


def domain_markers() -> tuple[str, ...]:
    return tuple(_domain_markers)


def conclusion_from_list_steps(steps: list[dict[str, Any]] | None) -> str | None:
    for formatter in _list_conclusion_formatters:
        text = formatter(steps)
        if isinstance(text, str) and text.strip():
            return text
    return None


def prefer_user_reply(raw: str, conclusions: list[str] | None) -> str:
    text = (raw or "").strip()
    for hook in _prefer_reply_hooks:
        text = hook(text, conclusions)
    return text


def apply_result_view(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    view = _result_views.get(tool_name or "")
    if view is None:
        return payload
    return view(payload)


def has_result_view(tool_name: str) -> bool:
    return (tool_name or "") in _result_views


def result_view_tool_names() -> frozenset[str]:
    return frozenset(_result_views)


def supplement_instruction_extra() -> str:
    """复核补查时追加的域提示（接在通用「补证据」句之后）。"""
    if not _supplement_hints:
        return "不要引用其他专家的结论作为证据；不要向用户索要手机号/账号。"
    return "；".join(_supplement_hints) + "。"


def human_cs_scope_blurb() -> str:
    return _human_cs_scope_blurb
