"""发给模型的上下文压缩：只改本次 LLM 请求视图，不删 checkpoint 里的 messages。

挂载：create_agent 中间件链 本模块 → HITL。
不在网关入口、不在 run_agent_loop 收尾、不在 after_agent 回写历史。

时机（每次即将调用聊天模型，含同一用户轮内「工具返回后再调模型」）：
- before_model：从当前内存 messages 合并 working_memory，写回图状态（随后进 checkpoint）。
- wrap_model_call：估窗；未超阈只给 system 追加槽 JSON；超阈则切最近 n 轮与 n 轮外。
  只规则压缩窗外，再对「窗外压缩结果 + n 轮」估窗；仍超则用摘要替换窗外再估；
  再超则截断或丢弃窗外。摘要替换窗外长段以减窗，不叠在 n 轮上。
  发出前 sanitize_tool_pairs：补齐或剥离未配对 tool_calls，避免 DeepSeek 拒识。

保留单位：用户轮，不是消息条数。一轮 = 一条 HumanMessage 起到下一条 Human 之前
（含中间 AI / Tool）。默认最近 context_keep_recent_turns 轮原文进模型，不与窗外混装。

判定不靠问候词/业务词表：旧轮有无 tool_calls/ToolMessage、JSON 是否含 list、
工具 policy.effect 是否 WRITE。ids 按键名形态（id / *Id / *No）从工具 JSON 抽取。

checkpoint 仍全量；压缩结果不 RemoveMessage。审计仍读全量 messages。
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from typing import Any, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately

from app.core.agent.graph_runtime import OrderAgentState, read_hitl_interrupt
from app.core.agent.tools.governance import Effect
from app.core.agent.tools.registry import TOOL_DEFINITIONS, slim_invoice_for_agent
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 标识键：只认形态，不写死 orderId 等业务字段名
_ID_KEY = re.compile(r"(^id$|Id$|_id$|No$|_no$)", re.I)
_WM_PREFIX = "[working_memory] "  # 注入 system 的槽前缀；已存在则替换该段
_SUMMARY_PREFIX = "[history_summary] "  # 超窗后旧段摘要，插在最近 K 轮之前
_LAST_USER_MAX = 120
_IDS_CAP = 40
_ARRAY_HEAD = 2  # 大数组保留头尾，避免轨迹/商品列表撑窗
_ARRAY_TAIL = 2
_ERROR_MSG_MAX = 400
_STUB_IDS_SHOW = 16

# 仅用于被裁掉且仍含工具活动的旧段；有则摘抄无则省略，禁止发挥
_SUMMARY_PROMPT = """从下列被裁掉的旧对话中摘抄要点。只输出 JSON 对象，有则填无则省略，禁止发挥、禁止改写标识符、禁止新意图、禁止抄日志全文。
可选键：goal, latest_instruction, constraints, acceptance, decisions, open_questions, interfaces, tool_outcomes, subagent, todos, blockers, risks, assumptions, next_action。
旧对话：
"""

_WRITE_TOOLS: frozenset[str] | None = None


def write_tool_names() -> frozenset[str]:
    """WRITE 工具名集合（认 ToolPolicy.effect，不认具体业务名）。"""
    global _WRITE_TOOLS
    if _WRITE_TOOLS is None:
        _WRITE_TOOLS = frozenset(
            item.name for item in TOOL_DEFINITIONS if item.policy.effect is Effect.WRITE
        )
    return _WRITE_TOOLS


def _text(content: Any) -> str:
    """抽出消息正文：兼容 str / 多段 content 列表。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)


def approx_tokens(
    messages: Sequence[Any],
    system: SystemMessage | None,
    *,
    tools: Sequence[Any] | None = None,
) -> int:
    """用 LangChain count_tokens_approximately 估窗。

    计入正文、role、name、AI tool_calls、Tool 的 tool_call_id；
    若有 tools 再计入 schema；若 AI 带 usage_metadata 则按最近一次真实 total_tokens 缩放。
    仍非 DeepSeek 官方 tokenizer，但比字符/4 覆盖更全。
    """
    packed: list[Any] = []
    if system is not None:
        packed.append(system)
    packed.extend(messages)
    if not packed:
        return 1
    return max(
        1,
        count_tokens_approximately(
            packed,
            extra_tokens_per_message=3.0,
            count_name=True,
            use_usage_metadata_scaling=True,
            tools=list(tools) if tools else None,
        ),
    )


def _parse_json(text: str) -> Any | None:
    """解析工具正文；失败则尝试截取第一个 { 到最后一个 }（兼容模型夹杂说明）。"""
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None


def _tool_name(msg: ToolMessage) -> str:
    return str(getattr(msg, "name", None) or "")


def _is_error_payload(data: Any) -> bool:
    """治理层失败体：ok=false 或带 error / error_code。"""
    if not isinstance(data, dict):
        return False
    if data.get("ok") is False:
        return True
    return bool(data.get("error") or data.get("error_code"))


def _is_list_payload(data: Any) -> bool:
    """列表形状：顶层 list[]，或带 page 且存在任一数组字段。不写死工具名。"""
    if not isinstance(data, dict):
        return False
    items = data.get("list")
    if isinstance(items, list):
        return True
    if isinstance(data.get("page"), int) and any(isinstance(data.get(k), list) for k in data):
        return True
    return False


def _collect_ids_from_obj(obj: Any, acc: list[str]) -> None:
    """递归收集标识字符串，供槽 ids / last_list 在丢掉列表原文后仍能指代。"""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str) and value and _ID_KEY.search(str(key)):
                if value not in acc:
                    acc.append(value)
            elif isinstance(value, (dict, list)):
                _collect_ids_from_obj(value, acc)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                _collect_ids_from_obj(item, acc)
            elif len(obj) < 30:
                _collect_ids_from_obj(item, acc)


def _row_slim(item: Any) -> Any:
    """列表行瘦身：只留标识键 + 标量 status；都没有则留前 3 个键以免变成空对象。"""
    if not isinstance(item, dict):
        return item
    slim: dict[str, Any] = {}
    for key, value in item.items():
        if isinstance(value, str) and _ID_KEY.search(str(key)):
            slim[key] = value
        elif str(key).lower() == "status" and not isinstance(value, (dict, list)):
            slim[key] = value
    return slim or {k: item[k] for k in list(item)[:3]}


def _truncate_arrays(value: Any, *, budget: int) -> Any:
    """超长数组留头尾 + omitted 计数；超长字符串截断。用于日志/轨迹，不按业务字段特判。"""
    if isinstance(value, dict):
        return {k: _truncate_arrays(v, budget=budget) for k, v in value.items()}
    if isinstance(value, list):
        if len(json.dumps(value, ensure_ascii=False)) <= budget and len(value) <= 8:
            return [_truncate_arrays(v, budget=budget) for v in value]
        head = [_truncate_arrays(v, budget=budget) for v in value[:_ARRAY_HEAD]]
        tail = [_truncate_arrays(v, budget=budget) for v in value[-_ARRAY_TAIL:]]
        return head + [{"_omitted": len(value) - _ARRAY_HEAD - _ARRAY_TAIL}] + tail
    if isinstance(value, str) and len(value) > budget:
        return value[:budget] + "…"
    return value


def slim_list_payload(data: dict[str, Any]) -> dict[str, Any]:
    """最新一次列表结果：行级瘦身后再按字符预算截断数组。"""
    out = dict(data)
    items = data.get("list")
    if isinstance(items, list):
        out["list"] = [_row_slim(x) for x in items]
        ids: list[str] = []
        _collect_ids_from_obj(items, ids)
        out["_ids"] = ids[:_IDS_CAP]
    return _truncate_arrays(out, budget=get_settings().context_tool_result_max_chars)


def list_index(data: dict[str, Any], tool: str) -> dict[str, Any]:
    """写入 last_list 的短索引：tool + 分页 + ids，替代整页 JSON。"""
    ids: list[str] = []
    items = data.get("list") if isinstance(data.get("list"), list) else None
    if items is not None:
        _collect_ids_from_obj(items, ids)
    else:
        _collect_ids_from_obj(data, ids)
    return {
        "tool": tool,
        "page": data.get("page"),
        "total": data.get("total"),
        "ids": ids[:_IDS_CAP],
    }


def stub_list(tool: str, data: dict[str, Any] | None) -> str:
    """更早的同名列表：占位字符串，细节指向 working_memory。"""
    idx = list_index(data, tool) if isinstance(data, dict) else {"tool": tool, "ids": []}
    shown = idx.get("ids") or []
    more = ""
    if len(shown) > _STUB_IDS_SHOW:
        shown, more = shown[:_STUB_IDS_SHOW], f" +{len(idx['ids']) - _STUB_IDS_SHOW}"
    return (
        f"[compressed] {tool} total={idx.get('total')} "
        f"ids={','.join(str(x) for x in shown)}{more} 详见 working_memory"
    )


def short_error(data: dict[str, Any]) -> str:
    """工具失败：只留 code + message，不当长日志。"""
    code = data.get("error_code") or (data.get("error") or {}).get("code") if isinstance(data.get("error"), dict) else data.get("error_code")
    msg = data.get("message") or (data.get("error") or {}).get("message") if isinstance(data.get("error"), dict) else data.get("message")
    text = f"ok=false error_code={code or ''} message={msg or ''}"
    return text[:_ERROR_MSG_MAX]


def replace_tool_content(msg: ToolMessage, content: str) -> ToolMessage:
    """换正文但保留 tool_call_id / name，避免拆散 AI↔Tool 对。"""
    return ToolMessage(
        content=content,
        tool_call_id=str(getattr(msg, "tool_call_id", "") or ""),
        name=_tool_name(msg) or None,
    )


def split_turns(messages: Sequence[AnyMessage]) -> list[list[AnyMessage]]:
    """按 HumanMessage 切轮。当前轮可以还没有最终 AI，仍算一轮且必须留下。"""
    turns: list[list[AnyMessage]] = []
    current: list[AnyMessage] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            if current:
                turns.append(current)
            current = [msg]
        else:
            current.append(msg)
    if current:
        turns.append(current)
    return turns


def _has_tool_activity(msgs: Sequence[AnyMessage]) -> bool:
    """该段是否「干过活」：有 tool_calls 或 ToolMessage。无则视为可丢的旧纯对话。"""
    for msg in msgs:
        if isinstance(msg, ToolMessage):
            return True
        if isinstance(msg, AIMessage) and (getattr(msg, "tool_calls", None) or []):
            return True
    return False


def merge_working_memory(
    previous: dict[str, Any] | None,
    messages: Sequence[AnyMessage],
) -> dict[str, Any]:
    """规则抽槽（不用 LLM）。后写覆盖。

    last_user：最新用户句，钉住当前指令。
    ids：工具 JSON 里的标识，只信工具结果。
    last_list：最近一次列表形状结果的短索引。
    last_write / last_error：写操作与失败摘要。
    goal/constraints 等摘要字段不在这里写，避免规则路径猜用户意图。
    """
    memory: dict[str, Any] = dict(previous or {})
    ids: list[str] = list(memory.get("ids") or []) if isinstance(memory.get("ids"), list) else []
    write_names = write_tool_names()

    for msg in messages:
        if isinstance(msg, HumanMessage):
            text = _text(msg.content).strip()
            if text:
                memory["last_user"] = text[:_LAST_USER_MAX]
            continue
        if not isinstance(msg, ToolMessage):
            continue
        data = _parse_json(_text(msg.content))
        name = _tool_name(msg)
        if data is not None:
            _collect_ids_from_obj(data, ids)
        if isinstance(data, dict) and _is_list_payload(data):
            memory["last_list"] = list_index(data, name)
        if isinstance(data, dict) and _is_error_payload(data):
            memory["last_error"] = {
                "tool": name,
                "error_code": data.get("error_code"),
                "message": str(data.get("message") or "")[:_ERROR_MSG_MAX],
            }
        if name in write_names:
            ok = not (isinstance(data, dict) and _is_error_payload(data))
            memory["last_write"] = {"tool": name, "ok": ok}
            if isinstance(data, dict) and not ok:
                memory["last_write"]["error_code"] = data.get("error_code")

    if ids:
        memory["ids"] = ids[-_IDS_CAP:]
    return memory


def _hitl_blockers() -> Any | None:
    """当前 thread 若挂起 HITL，记为 blockers，避免压缩后模型忘掉待批。"""
    try:
        hitl = read_hitl_interrupt()
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(hitl, dict):
        return None
    requests = hitl.get("action_requests") or []
    tools = []
    for item in requests:
        if isinstance(item, dict) and item.get("name"):
            tools.append(item.get("name"))
    if not tools:
        return None
    return {"tools": tools, "summary": (hitl.get("description") or "")[:200]}


def _overweight(messages: Sequence[AnyMessage], max_chars: int) -> bool:
    """单条过肥：即使总条数/token 未超阈也要压，避免一页 list 污染指代。"""
    for msg in messages:
        if isinstance(msg, ToolMessage) and len(_text(msg.content)) > max_chars:
            return True
        if isinstance(msg, AIMessage) and not (getattr(msg, "tool_calls", None) or []):
            if len(_text(msg.content)) > max_chars:
                return True
    return False


def _over_budget(
    messages: Sequence[AnyMessage],
    system: SystemMessage | None,
    *,
    tools: Sequence[Any] | None = None,
) -> bool:
    """条数或近似 token 超阈（不含单条过肥；过肥只用于是否启动压缩）。"""
    settings = get_settings()
    if len(messages) >= settings.context_compress_max_messages:
        return True
    return approx_tokens(messages, system, tools=tools) >= settings.context_compress_max_tokens


def _should_compress(
    messages: Sequence[AnyMessage],
    system: SystemMessage | None,
    *,
    tools: Sequence[Any] | None = None,
) -> bool:
    """触发：条数 或 近似 token 或 单条过肥，任一满足即裁 request.messages。"""
    if _over_budget(messages, system, tools=tools):
        return True
    return _overweight(messages, get_settings().context_tool_result_max_chars)


def _call_id(call: Any) -> str:
    if isinstance(call, dict):
        return str(call.get("id") or "")
    return str(getattr(call, "id", "") or "")


def _call_name(call: Any) -> str:
    if isinstance(call, dict):
        return str(call.get("name") or "")
    return str(getattr(call, "name", "") or "")


_MISSING_TOOL_RESULT = "[tool_result_missing] 该次工具调用未完成或已从上下文省略。"


def sanitize_tool_pairs(messages: Sequence[AnyMessage]) -> list[AnyMessage]:
    """发给模型前保证：有 tool_calls 的 AI 后面跟齐对应 ToolMessage。

    只改本次请求视图。孤立 Tool 丢掉；历史中间缺观察则补占位；
    末尾尚无任何 Tool 的 tool_calls 去掉（避免把未执行调用伪装成已完成）。
    """
    src = list(messages)
    out: list[AnyMessage] = []
    i = 0
    n = len(src)
    while i < n:
        msg = src[i]
        if isinstance(msg, ToolMessage):
            i += 1
            continue
        if not isinstance(msg, AIMessage):
            out.append(msg)
            i += 1
            continue
        calls = list(getattr(msg, "tool_calls", None) or [])
        if not calls:
            out.append(msg)
            i += 1
            continue
        needed = [(_call_id(c), _call_name(c)) for c in calls if _call_id(c)]
        if not needed:
            text = _text(msg.content).strip()
            if text:
                out.append(AIMessage(content=text))
            j = i + 1
            while j < n and isinstance(src[j], ToolMessage):
                j += 1
            i = j
            continue
        j = i + 1
        found: dict[str, ToolMessage] = {}
        while j < n and isinstance(src[j], ToolMessage):
            tc = str(getattr(src[j], "tool_call_id", "") or "")
            if tc and tc not in found:
                found[tc] = src[j]
            j += 1
        missing = [(cid, name) for cid, name in needed if cid not in found]
        trailing_unexecuted = j >= n and not found
        if trailing_unexecuted:
            text = _text(msg.content).strip()
            if text:
                out.append(AIMessage(content=text))
            i = j
            continue
        out.append(msg)
        for cid, _name in needed:
            if cid in found:
                out.append(found[cid])
        for cid, name in missing:
            out.append(
                ToolMessage(
                    content=_MISSING_TOOL_RESULT,
                    tool_call_id=cid,
                    name=name or None,
                )
            )
        i = j
    return out


def _ensure_tool_pairs(messages: list[AnyMessage], src: Sequence[AnyMessage]) -> list[AnyMessage]:
    """切窗口落到孤立 ToolMessage 时，从原文补回带 tool_calls 的 AI，避免模型再编观察。"""
    ids_needed = {
        str(getattr(msg, "tool_call_id", "") or "")
        for msg in messages
        if isinstance(msg, ToolMessage)
    }
    have_ai = {
        _call_id(call)
        for msg in messages
        if isinstance(msg, AIMessage)
        for call in (getattr(msg, "tool_calls", None) or [])
    }
    missing = ids_needed - have_ai - {""}
    if not missing:
        return messages
    extra: list[AnyMessage] = []
    for msg in src:
        if not isinstance(msg, AIMessage):
            continue
        calls = getattr(msg, "tool_calls", None) or []
        if any(_call_id(c) in missing for c in calls):
            extra.append(msg)
    return extra + messages


def _transform_kept(
    kept: list[AnyMessage],
    *,
    all_messages: Sequence[AnyMessage],
) -> list[AnyMessage]:
    """最近 K 轮内部仍可瘦身：最新 list 留 id/status；更早同名 list 改占位；错误缩短。"""
    settings = get_settings()
    max_chars = settings.context_tool_result_max_chars
    last_list_idx: dict[str, int] = {}
    parsed: dict[int, Any] = {}
    for idx, msg in enumerate(kept):
        if not isinstance(msg, ToolMessage):
            continue
        data = _parse_json(_text(msg.content))
        parsed[idx] = data
        name = _tool_name(msg)
        if isinstance(data, dict) and _is_list_payload(data) and name:
            last_list_idx[name] = idx

    write_names = write_tool_names()
    out: list[AnyMessage] = []
    for idx, msg in enumerate(kept):
        if not isinstance(msg, ToolMessage):
            if isinstance(msg, AIMessage) and not (getattr(msg, "tool_calls", None) or []):
                if len(_text(msg.content)) > max_chars:
                    out.append(AIMessage(content=_text(msg.content)[:max_chars] + "…"))
                    continue
            out.append(msg)
            continue
        data = parsed.get(idx)
        name = _tool_name(msg)
        if isinstance(data, dict) and _is_error_payload(data):
            out.append(replace_tool_content(msg, short_error(data)))
            continue
        if name == "get_invoice" and isinstance(data, dict):
            # 旧线程可能仍含 email /「已发送邮箱」；送模前再剥一次
            slim = slim_invoice_for_agent(data)
            out.append(replace_tool_content(msg, json.dumps(slim, ensure_ascii=False)))
            continue
        if isinstance(data, dict) and _is_list_payload(data) and name:
            if last_list_idx.get(name) == idx:
                slim = slim_list_payload(data)
                out.append(replace_tool_content(msg, json.dumps(slim, ensure_ascii=False)))
            else:
                out.append(replace_tool_content(msg, stub_list(name, data)))
            continue
        if name in write_names and isinstance(data, dict):
            brief = json.dumps(
                {k: data[k] for k in list(data)[:8]},
                ensure_ascii=False,
            )
            if len(_text(msg.content)) > max_chars:
                out.append(replace_tool_content(msg, brief[:max_chars] + "…"))
                continue
        if len(_text(msg.content)) > max_chars:
            if isinstance(data, dict):
                trimmed = _truncate_arrays(data, budget=max_chars)
                out.append(replace_tool_content(msg, json.dumps(trimmed, ensure_ascii=False)))
            else:
                out.append(replace_tool_content(msg, _text(msg.content)[:max_chars] + "…"))
            continue
        out.append(msg)
    return _ensure_tool_pairs(out, all_messages)


def _force_from_dropped(
    dropped: Sequence[AnyMessage],
    kept: Sequence[AnyMessage],
) -> list[AnyMessage]:
    """n 轮外的短事实：最后一次错误、WRITE 占位。只进窗外压缩结果，不并入 kept。"""
    if not dropped:
        return []
    # 对象身份：同一条消息若已在最近 K 轮里，后面不再塞一遍
    kept_ids = {id(m) for m in kept}
    extra: list[AnyMessage] = []
    last_error: ToolMessage | None = None
    last_write: ToolMessage | None = None
    write_names = write_tool_names()

    dropped_list = list(dropped)
    for msg in dropped_list:
        if not isinstance(msg, ToolMessage):
            continue
        data = _parse_json(_text(msg.content))
        name = _tool_name(msg)
        # 扫完全部旧 Tool，只留「最后一次」失败，避免把历史错误堆进窗口
        if isinstance(data, dict) and _is_error_payload(data):
            last_error = replace_tool_content(msg, short_error(data))
        # WRITE 同样只留最后一次短结果；list 形状用占位，其它只留 tool+ok
        if name in write_names:
            last_write = replace_tool_content(
                msg,
                stub_list(name, data) if isinstance(data, dict) and _is_list_payload(data) else json.dumps({"tool": name, "ok": not (isinstance(data, dict) and _is_error_payload(data))}, ensure_ascii=False),
            )
    if last_error is not None:
        extra.append(last_error)
    if last_write is not None:
        extra.append(last_write)
    # tool_call_id 去重：最近 K 轮已有对应 Tool 观察则不再用旧段那条
    kept_tc = {
        str(getattr(m, "tool_call_id", "") or "")
        for m in kept
        if isinstance(m, ToolMessage)
    }
    filtered: list[AnyMessage] = []
    for msg in extra:
        if id(msg) in kept_ids:
            continue
        if isinstance(msg, ToolMessage) and str(getattr(msg, "tool_call_id", "") or "") in kept_tc:
            continue
        filtered.append(msg)
    return filtered


def _dropped_text(dropped: Sequence[AnyMessage], *, limit: int = 12000) -> str:
    """摘要模型的输入：旧段截断拼接，避免把被裁全文再喂回去。"""
    chunks: list[str] = []
    for msg in dropped:
        role = type(msg).__name__
        chunks.append(f"{role}: {_text(msg.content)[:800]}")
        if sum(len(c) for c in chunks) >= limit:
            break
    return "\n".join(chunks)[:limit]


def _merge_summary_fields(memory: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    """摘要只补空槽；规则已写入的 last_user/ids/last_write 等不被摘要改掉。"""
    allowed = (
        "goal",
        "latest_instruction",
        "constraints",
        "acceptance",
        "decisions",
        "open_questions",
        "interfaces",
        "tool_outcomes",
        "subagent",
        "todos",
        "blockers",
        "risks",
        "assumptions",
        "next_action",
    )
    out = dict(memory)
    for key in allowed:
        if key in out and out[key] not in (None, "", [], {}):
            continue
        if key in parsed and parsed[key] not in (None, "", [], {}):
            out[key] = parsed[key]
    return out


def _try_summarize(request: ModelRequest, dropped: Sequence[AnyMessage]) -> str | None:
    """用短 JSON 替换已规则压缩的 n 轮外，以减窗。直调 request.model，绕过本中间件。

    失败返回 None，由调用方截断窗外。纯寒暄不调模型。禁止编造。
    """
    if not dropped or not _has_tool_activity(dropped):
        return None
    prompt = _SUMMARY_PROMPT + _dropped_text(dropped)
    try:
        result = request.model.invoke([HumanMessage(content=prompt)])
        text = _text(getattr(result, "content", result))
    except Exception:  # noqa: BLE001
        logger.warning("context summary invoke failed", exc_info=True)
        return None
    parsed = _parse_json(text)
    if isinstance(parsed, dict):
        return json.dumps(parsed, ensure_ascii=False)
    text = (text or "").strip()
    return text[:2000] if text else None


def inject_system(system: SystemMessage | None, memory: dict[str, Any]) -> SystemMessage | None:
    """把槽贴到 system 末尾。压缩器不改人设正文，只替换已有 [working_memory] 段。"""
    payload = {k: v for k, v in memory.items() if v not in (None, "", [], {})}
    if not payload:
        return system
    block = _WM_PREFIX + json.dumps(payload, ensure_ascii=False)
    if system is None:
        return SystemMessage(content=block)
    base = _text(system.content)
    if _WM_PREFIX in base:
        base = base.split(_WM_PREFIX)[0].rstrip()
    return SystemMessage(content=base + "\n\n" + block)


def _outside_disjoint(
    outside: Sequence[AnyMessage],
    kept: Sequence[AnyMessage],
) -> list[AnyMessage]:
    """窗外与 n 轮不相交：去掉已在 kept 的对象与相同 tool_call_id；窗外内部 tool_call_id 去重。"""
    kept_ids = {id(m) for m in kept}
    kept_tc = {
        str(getattr(m, "tool_call_id", "") or "")
        for m in kept
        if isinstance(m, ToolMessage)
    }
    seen_ids: set[int] = set()
    seen_tc: set[str] = set()
    out: list[AnyMessage] = []
    for msg in outside:
        if id(msg) in kept_ids or id(msg) in seen_ids:
            continue
        if isinstance(msg, ToolMessage):
            tc = str(getattr(msg, "tool_call_id", "") or "")
            if tc and (tc in kept_tc or tc in seen_tc):
                continue
            if tc:
                seen_tc.add(tc)
        seen_ids.add(id(msg))
        out.append(msg)
    return out


def compress_messages(
    messages: Sequence[AnyMessage],
    *,
    memory: dict[str, Any],
) -> tuple[list[AnyMessage], list[AnyMessage]]:
    """切最近 n 轮与 n 轮外。只规则压缩窗外；n 轮仅轮内瘦 Tool。不改 checkpoint。

    返回 (kept_n, outside_compressed)。不相交。旧轮无 tool 则丢；error/WRITE stub 只在窗外。
    """
    del memory
    keep_n = max(1, int(get_settings().context_keep_recent_turns))
    turns = split_turns(messages)
    kept_turns = turns[-keep_n:] if turns else []
    outside_turns = turns[:-keep_n] if len(turns) > keep_n else []
    kept = [m for turn in kept_turns for m in turn]
    toolish: list[AnyMessage] = []
    for turn in outside_turns:
        if _has_tool_activity(turn):
            toolish.extend(turn)
    extra = _force_from_dropped(toolish, kept)
    kept = _transform_kept(kept, all_messages=kept)
    transformed = _transform_kept(toolish, all_messages=toolish)
    outside = _outside_disjoint(transformed + list(extra), kept)
    return kept, outside


class ContextCompressionMiddleware(AgentMiddleware[OrderAgentState]):
    """压缩中间件。state_schema 带 working_memory，与 create_agent 的 OrderAgentState 对齐。"""

    state_schema = OrderAgentState

    def before_model(self, state: OrderAgentState, runtime: Any) -> dict[str, Any] | None:
        """每跳模型前合槽。不改 messages。HITL 解除后清 blockers。"""
        del runtime
        messages = state.get("messages") or []
        prev = state.get("working_memory")
        memory = merge_working_memory(prev if isinstance(prev, dict) else None, messages)
        blockers = _hitl_blockers()
        if blockers:
            memory["blockers"] = blockers
        elif "blockers" in memory and not blockers:
            memory.pop("blockers", None)
        return {"working_memory": memory}

    def _prepare(self, request: ModelRequest) -> ModelRequest:
        """切 n 轮 / 压窗外 / 估窗；仍超则摘要替换窗外再估；再超则截断窗外。"""
        messages = list(request.messages or [])
        state = request.state if isinstance(request.state, dict) else {}
        memory = state.get("working_memory") if isinstance(state.get("working_memory"), dict) else {}
        if not memory:
            memory = merge_working_memory(None, messages)
        system = inject_system(request.system_message, memory)
        # 未超阈：不裁消息，仍注入槽，保证指代锚点始终在窗顶
        tools = request.tools or None
        if not _should_compress(messages, request.system_message, tools=tools):
            if system is request.system_message:
                prepared = request
            else:
                prepared = request.override(system_message=system)
        else:
            kept, outside = compress_messages(messages, memory=memory)
            view = outside + kept
            prepared = None
            if not _over_budget(view, system, tools=tools):
                prepared = request.override(messages=view, system_message=system)
            elif outside:
                summary = _try_summarize(request, outside)
                if summary:
                    cand_system = system
                    parsed = _parse_json(summary)
                    if isinstance(parsed, dict):
                        merged = _merge_summary_fields(memory, parsed)
                        cand_system = inject_system(request.system_message, merged)
                    summary_view = [HumanMessage(content=_SUMMARY_PREFIX + summary)] + kept
                    if not _over_budget(summary_view, cand_system, tools=tools):
                        prepared = request.override(
                            messages=summary_view, system_message=cand_system
                        )
                if prepared is None:
                    trimmed = _aggressive_trim(outside)
                    trim_view = trimmed + kept
                    if not _over_budget(trim_view, system, tools=tools):
                        prepared = request.override(messages=trim_view, system_message=system)
            if prepared is None:
                prepared = request.override(messages=kept, system_message=system)
        prepared_msgs = _strip_invoice_email_tool_messages(list(prepared.messages or []))
        prepared = prepared.override(messages=sanitize_tool_pairs(prepared_msgs))
        if _tool_rounds_this_turn(messages) >= get_settings().agent_max_tool_rounds:
            prepared = _force_text_only(prepared)
        return prepared

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """同步路径（invoke）：压缩视图后再真正调模型。"""
        return handler(self._prepare(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable,
    ) -> ModelResponse:
        """异步路径（astream）：与 wrap_model_call 同一套 _prepare。"""
        return await handler(self._prepare(request))


def _strip_invoice_email_tool_messages(messages: list[AnyMessage]) -> list[AnyMessage]:
    """无论是否压缩，历史 get_invoice 结果送模前剥离 email / 发信进度。"""
    out: list[AnyMessage] = []
    for msg in messages:
        if not isinstance(msg, ToolMessage) or _tool_name(msg) != "get_invoice":
            out.append(msg)
            continue
        data = _parse_json(_text(msg.content))
        if not isinstance(data, dict):
            out.append(msg)
            continue
        slim = slim_invoice_for_agent(data)
        out.append(replace_tool_content(msg, json.dumps(slim, ensure_ascii=False)))
    return out


def _tool_rounds_this_turn(messages: Sequence[AnyMessage]) -> int:
    """当前用户轮里，带 tool_calls 的 AI 条数。"""
    n = 0
    for msg in reversed(list(messages)):
        if isinstance(msg, HumanMessage):
            break
        if isinstance(msg, AIMessage) and (getattr(msg, "tool_calls", None) or []):
            n += 1
    return n


def _force_text_only(request: ModelRequest) -> ModelRequest:
    """达到工具轮次上限：去掉 tools，避免模型空转撞 recursion_limit。"""
    note = (
        "【系统】本轮工具调用已达上限，请仅根据已有结果用中文 Markdown 给出最终答复，"
        "禁止再调用任何工具。"
    )
    system = request.system_message
    if system is None:
        system = SystemMessage(content=note)
    else:
        system = SystemMessage(content=_text(system.content).rstrip() + "\n\n" + note)
    return request.override(tools=[], system_message=system)


def _aggressive_trim(messages: list[AnyMessage]) -> list[AnyMessage]:
    """只截断 n 轮外：长 Tool 改占位，不编造 history_summary、不动最近 n 轮。"""
    out: list[AnyMessage] = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and len(_text(msg.content)) > 400:
            name = _tool_name(msg) or "tool"
            data = _parse_json(_text(msg.content))
            if isinstance(data, dict) and _is_list_payload(data):
                out.append(replace_tool_content(msg, stub_list(name, data)))
            else:
                out.append(replace_tool_content(msg, f"[compressed] {name} len={len(_text(msg.content))}"))
            continue
        out.append(msg)
    return out
