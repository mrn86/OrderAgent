"""工具循环硬停：去重 + 达上限后去掉 tool_calls 并结束图。

根因不是 25 这个数字本身：create_agent 把每个 before_model/after_model 都做成图节点，
模型只要再发一轮 tool_calls，图就到不了 END。去掉 tools 不够——DeepSeek 仍可能继续
吐 tool_calls，路由会再进 tools 节点。这里在模型输出上剥掉 tool_calls，并 jump_to end。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import (
    ModelRequest,
    ModelResponse,
    hook_config,
)
from langchain_core.messages import AIMessage, AnyMessage, RemoveMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from app.core.agent.compression import _text, _tool_rounds_this_turn
from app.core.agent.graph_runtime import OrderAgentState
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_FALLBACK_ANSWER = "已根据已有查询结果整理完毕。若还需要某一笔订单的明细，请告诉我订单号。"
_DUP_SKIP = (
    "该工具已用相同参数成功执行过，请直接根据已有结果用中文答复用户，禁止再次调用同一工具。"
)


def tool_call_fingerprint(name: str, args: Any) -> str:
    try:
        payload = json.dumps(args or {}, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        payload = str(args)
    return f"{name}:{payload}"


def _ai_text(msg: AIMessage) -> str:
    return _text(msg.content).strip()


def strip_tool_calls_from_response(response: Any) -> Any:
    """模型在无 tools 时仍可能吐 tool_calls；剥掉后图才会走向 END。"""
    if isinstance(response, AIMessage):
        if not (getattr(response, "tool_calls", None) or []):
            return response
        return AIMessage(content=_ai_text(response) or _FALLBACK_ANSWER, id=getattr(response, "id", None))

    result = getattr(response, "result", None)
    if not isinstance(result, list):
        return response
    new_msgs: list[Any] = []
    changed = False
    for msg in result:
        if isinstance(msg, AIMessage) and (getattr(msg, "tool_calls", None) or []):
            new_msgs.append(
                AIMessage(content=_ai_text(msg) or _FALLBACK_ANSWER, id=getattr(msg, "id", None))
            )
            changed = True
        else:
            new_msgs.append(msg)
    if not changed:
        return response
    return ModelResponse(
        result=new_msgs,
        structured_response=getattr(response, "structured_response", None),
    )


def _over_tool_round_limit(messages: Sequence[AnyMessage]) -> bool:
    return _tool_rounds_this_turn(messages) >= get_settings().agent_max_tool_rounds


class ToolLoopGuardMiddleware(AgentMiddleware[OrderAgentState]):
    """同一用户轮：重复工具短接；达上限后强制最终文本并结束图。"""

    state_schema = OrderAgentState

    def __init__(self) -> None:
        super().__init__()
        self._ok_results: dict[str, str] = {}

    def _force_text_request(self, request: ModelRequest) -> ModelRequest:
        note = (
            "【系统】本轮工具调用已达上限或出现重复查询，请仅根据已有结果用中文 Markdown "
            "给出最终答复，禁止再调用任何工具。"
        )
        system = request.system_message
        if system is None:
            from langchain_core.messages import SystemMessage

            system = SystemMessage(content=note)
        else:
            from langchain_core.messages import SystemMessage

            system = SystemMessage(content=_text(system.content).rstrip() + "\n\n" + note)
        return request.override(tools=[], tool_choice=None, system_message=system)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse | AIMessage:
        prepared = request
        if _over_tool_round_limit(request.messages or []):
            prepared = self._force_text_request(request)
        response = handler(prepared)
        if _over_tool_round_limit(request.messages or []):
            return strip_tool_calls_from_response(response)
        return response

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable,
    ) -> ModelResponse | AIMessage:
        prepared = request
        if _over_tool_round_limit(request.messages or []):
            prepared = self._force_text_request(request)
        response = await handler(prepared)
        if _over_tool_round_limit(request.messages or []):
            return strip_tool_calls_from_response(response)
        return response

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Any],
    ) -> ToolMessage | Any:
        call = request.tool_call if isinstance(request.tool_call, dict) else {}
        name = str(call.get("name") or "")
        key = tool_call_fingerprint(name, call.get("args"))
        call_id = str(call.get("id") or "")
        if key in self._ok_results:
            logger.info("skip duplicate tool call name=%s", name)
            return ToolMessage(content=_DUP_SKIP, tool_call_id=call_id, name=name or None)
        result = handler(request)
        self._remember_if_ok(key, result)
        return result

    async def awrap_tool_call(self, request: ToolCallRequest, handler: Callable) -> ToolMessage | Any:
        call = request.tool_call if isinstance(request.tool_call, dict) else {}
        name = str(call.get("name") or "")
        key = tool_call_fingerprint(name, call.get("args"))
        call_id = str(call.get("id") or "")
        if key in self._ok_results:
            logger.info("skip duplicate tool call name=%s", name)
            return ToolMessage(content=_DUP_SKIP, tool_call_id=call_id, name=name or None)
        result = await handler(request)
        self._remember_if_ok(key, result)
        return result

    def _remember_if_ok(self, key: str, result: Any) -> None:
        content = result.content if isinstance(result, ToolMessage) else result
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, default=str)
        try:
            data = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            self._ok_results[key] = text
            return
        if isinstance(data, dict) and (data.get("ok") is False or data.get("error") or data.get("error_code")):
            return
        self._ok_results[key] = text

    def _pending_already_done(self, last: AIMessage) -> bool:
        calls = list(getattr(last, "tool_calls", None) or [])
        if not calls:
            return False
        for call in calls:
            if isinstance(call, dict):
                name, args = call.get("name"), call.get("args")
            else:
                name, args = getattr(call, "name", ""), getattr(call, "args", {})
            if tool_call_fingerprint(str(name or ""), args) not in self._ok_results:
                return False
        return True

    def _end_without_tools(self, last: AIMessage | None) -> dict[str, Any]:
        text = _ai_text(last) if last is not None else ""
        text = text or _FALLBACK_ANSWER
        patch: dict[str, Any] = {"jump_to": "end"}
        if last is not None and (getattr(last, "tool_calls", None) or []):
            if getattr(last, "id", None):
                patch["messages"] = [RemoveMessage(id=last.id), AIMessage(content=text)]
            else:
                patch["messages"] = [AIMessage(content=text)]
        return patch

    @hook_config(can_jump_to=["end"])
    def after_model(self, state: OrderAgentState, runtime: Any) -> dict[str, Any] | None:
        del runtime
        messages = list(state.get("messages") or [])
        last = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if last is None:
            return None
        if self._pending_already_done(last) or _over_tool_round_limit(messages):
            return self._end_without_tools(last)
        return None

    @hook_config(can_jump_to=["end"])
    async def aafter_model(self, state: OrderAgentState, runtime: Any) -> dict[str, Any] | None:
        return self.after_model(state, runtime)
