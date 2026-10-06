"""AgentLoop：组装 LLM + Tools，执行工具调用循环，并向外吐出结构化事件。

两种入口：
- run_agent_loop: 同步跑完，返回最终 answer / steps / humanCs
- stream_agent_loop: 异步逐步 yield SSE 事件（status/token/tool_*/human_cs/done）

高风险写工具：HumanInTheLoopMiddleware 在执行前 interrupt，
经 Command(resume) 批准/拒绝后继续。

人工客服策略：
1. 主 Agent 意图不清或超范围时调用 escalate_to_human_cs；
2. 若未主动 escalate，结束后按答复情况强制补发。
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import Any, AsyncIterator, Iterator, Optional

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from app.core.agent.compression import ContextCompressionMiddleware
from app.core.agent.loop_guard import ToolLoopGuardMiddleware
from app.core.agent.graph_runtime import (
    OrderAgentState,
    bind_runtime,
    get_checkpointer,
    read_hitl_interrupt,
    reset_runtime,
    thread_config,
)
from app.core.agent.human_cs import (
    build_human_cs_payload,
    has_escalate_step,
    human_cs_fallback_answer,
    should_force_human_cs,
)
from app.core.agent.llm import build_llm
from app.core.agent.tools import (
    format_hitl_summary,
    get_agent_tools,
    hitl_interrupt_on,
    resolve_execution_context,
)
from app.core.agent.tools.permissions import (
    ExecutionContext,
    reset_execution_context,
    set_execution_context,
)
from app.core.audit import (
    ensure_audit_request_id,
    get_trace_id,
    reset_agent_audit,
    start_agent_audit,
)
from app.core.context import ensure_conversation, touch_conversation
from app.gateway.prompts import PROMPT_KEY_AGENT_SYSTEM, get_enabled_prompt

logger = logging.getLogger(__name__)


def build_agent(ctx: ExecutionContext | None = None):
    """创建带 checkpointer + 上下文压缩 + HITL 的 Agent 图。"""
    llm = build_llm()
    tools = get_agent_tools(ctx)
    prompt = get_enabled_prompt(PROMPT_KEY_AGENT_SYSTEM)
    interrupt_on = hitl_interrupt_on()
    middleware = [ContextCompressionMiddleware(), ToolLoopGuardMiddleware()]
    if interrupt_on:
        middleware.append(
            HumanInTheLoopMiddleware(
                interrupt_on=interrupt_on,
                description_prefix="高风险写操作待审批",
            )
        )
    # create_agent 已绑定 recursion_limit=9999。这里再 with_config(80) 会覆盖它；
    # invoke 若带上默认 25，图会在正常工具轮次上先炸。停机靠 ToolLoopGuard。
    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=prompt.content,
        state_schema=OrderAgentState,
        checkpointer=get_checkpointer(),
        middleware=middleware,
        debug=False,
    )


def _bind_ctx_trace(base_ctx: ExecutionContext) -> ExecutionContext:
    ensure_audit_request_id()
    trace_id = get_trace_id()
    if trace_id and base_ctx.trace_id != trace_id:
        return replace(base_ctx, trace_id=trace_id)
    return base_ctx


def _start_turn_audit(base_ctx: ExecutionContext):
    prompt = get_enabled_prompt(PROMPT_KEY_AGENT_SYSTEM)
    return start_agent_audit(
        user_id=base_ctx.user_id,
        conversation_id=base_ctx.conversation_id or None,
        prompt_type=prompt.prompt_key,
        prompt_version=prompt.version,
        prompt_content=prompt.content,
    )


def _safe_finish_audit(session, audit_token, *, status: str, model_result: str | None) -> None:
    try:
        if session is not None:
            session.finish(status=status, model_result=model_result)
    except Exception:  # noqa: BLE001
        logger.warning("agent_turn audit finish failed", exc_info=True)
    finally:
        if audit_token is not None:
            try:
                reset_agent_audit(audit_token)
            except Exception:  # noqa: BLE001
                pass


def _ingest_messages_for_audit(session, messages: list[Any]) -> None:
    if session is None:
        return
    for msg in messages:
        if isinstance(msg, AIMessage):
            session.add_model_message(msg)


def _turn_input(query: str) -> dict[str, list[HumanMessage]]:
    """只提交本轮用户句；历史由 checkpointer 按 thread 恢复。"""
    return {"messages": [HumanMessage(content=query)]}


def _extract_text(content: Any) -> str:
    """从模型 chunk/content 中提取纯文本（兼容 str / 多段 content 列表）。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            else:
                text = getattr(item, "text", None)
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return str(content)


def _serialize_tool_io(value: Any) -> Any:
    """规范化工具入参/出参，尽量转为 JSON 可序列化结构。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return str(value)


def _chunk_has_tool_calls(chunk: Any) -> bool:
    """判断流式 chunk 是否属于「工具调用」阶段（此时文本多为旁白，应丢弃）。"""
    if chunk is None:
        return False
    if getattr(chunk, "tool_call_chunks", None):
        return True
    if getattr(chunk, "tool_calls", None):
        return True
    additional = getattr(chunk, "additional_kwargs", None) or {}
    return bool(additional.get("tool_calls") or additional.get("tool_call_chunks"))


def _approval_from_hitl(
    hitl: dict[str, Any],
    conversation_id: str,
) -> dict[str, Any] | None:
    """将 HITLRequest 转为前端 approval_required 载荷。requestId=thread_id。"""
    actions = hitl.get("action_requests") or []
    if not actions:
        return None
    action = actions[0] if isinstance(actions[0], dict) else {}
    tool = str(action.get("name") or "")
    args = action.get("args") if isinstance(action.get("args"), dict) else {}
    if not args and isinstance(action.get("arguments"), dict):
        args = action["arguments"]
    summary = str(action.get("description") or "").strip()
    if not summary:
        summary = format_hitl_summary(tool, args)
    return {
        "requestId": conversation_id,
        "tool": tool,
        "args": args,
        "summary": summary,
        "conversationId": conversation_id,
    }


def _approval_required_event(payload: dict[str, Any], conversation_id: str) -> dict[str, Any]:
    return {
        "type": "approval_required",
        "requestId": payload.get("requestId") or conversation_id,
        "tool": payload.get("tool"),
        "args": payload.get("args") or {},
        "summary": payload.get("summary") or "",
        "conversationId": conversation_id,
    }


def _messages_to_steps_answer(messages: list[Any]) -> tuple[list[dict[str, Any]], str]:
    steps: list[dict[str, Any]] = []
    answer = ""
    for msg in messages:
        if isinstance(msg, AIMessage):
            tool_calls = getattr(msg, "tool_calls", None) or []
            for call in tool_calls:
                steps.append(
                    {
                        "tool": call.get("name"),
                        "input": call.get("args"),
                        "observation": None,
                    }
                )
            if tool_calls:
                continue
            if msg.content:
                answer = _extract_text(msg.content)
        elif isinstance(msg, ToolMessage):
            for step in reversed(steps):
                if step.get("observation") is None:
                    step["observation"] = msg.content
                    break
    return steps, answer


def _attach_forced_human_cs(
    *,
    query: str,
    steps: list[dict[str, Any]],
    answer: str,
) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
    """在 Agent 结束后确保 humanCs 可用。"""
    human_cs = None
    for step in steps:
        if step.get("tool") == "escalate_to_human_cs":
            obs = step.get("observation")
            if isinstance(obs, dict) and obs.get("csUrl"):
                human_cs = obs
            elif isinstance(obs, str):
                try:
                    parsed = json.loads(obs)
                    if isinstance(parsed, dict) and parsed.get("csUrl"):
                        human_cs = parsed
                except Exception:
                    pass
            break

    force_reason = should_force_human_cs(query, steps, answer)
    if force_reason and not human_cs:
        human_cs = build_human_cs_payload(force_reason)
        steps = list(steps) + [
            {
                "tool": "escalate_to_human_cs",
                "input": {"reason": force_reason},
                "observation": human_cs,
            }
        ]
        if not answer or force_reason not in answer:
            answer = human_cs_fallback_answer(force_reason)
    elif has_escalate_step(steps) and not human_cs:
        human_cs = build_human_cs_payload("当前问题无法自动处理")

    return answer, steps, human_cs


def _public_exc_message(exc: BaseException) -> str:
    if isinstance(exc, GraphRecursionError) or "Recursion limit of" in str(exc):
        return "本轮推理步数过多已自动停止。请精简问题，或新开对话后再试。"
    return str(exc).strip() or type(exc).__name__


def _pending_approval_answer(summary: str) -> str:
    text = (summary or "").strip()
    if text:
        return f"{text}。请在下方确认是否批准执行。"
    return "该操作属于高风险写操作，请在下方确认是否批准执行。"


def _pending_hitl(
    cid: str,
) -> tuple[dict[str, Any], dict[str, Any] | None, str] | None:
    """会话上若已有未审批 interrupt，禁止再塞新 Human（否则 tool_calls 无 Tool 回包）。"""
    hitl = read_hitl_interrupt(cid)
    if hitl is None:
        return None
    approval = _approval_from_hitl(hitl, cid)
    answer = _pending_approval_answer((approval or {}).get("summary") or "")
    return hitl, approval, answer


def run_agent_loop(
    query: str,
    conversation_id: Optional[str] = None,
    *,
    execution_ctx: ExecutionContext | None = None,
) -> dict[str, Any]:
    """同步执行 AgentLoop，返回完整结果。"""
    cid = ensure_conversation(conversation_id)
    user_query = (query or "").strip()
    runtime_tokens = None
    token = None
    audit_session = None
    audit_token = None
    try:
        base_ctx = _bind_ctx_trace(
            replace(
                resolve_execution_context(execution_ctx),
                user_query=user_query,
                conversation_id=cid,
            )
        )
        audit_session, audit_token = _start_turn_audit(base_ctx)
        agent = build_agent(base_ctx)
        runtime_tokens = bind_runtime(agent, cid)
        token = set_execution_context(base_ctx)

        blocked = _pending_hitl(cid)
        if blocked is not None:
            _hitl, approval, answer = blocked
            touch_conversation(cid)
            _safe_finish_audit(
                audit_session, audit_token, status="approval_required", model_result=answer
            )
            audit_token = None
            result = {
                "query": user_query,
                "answer": answer,
                "steps": [],
                "humanCs": None,
                "conversationId": cid,
            }
            if approval:
                result["approvalRequired"] = approval
            return result

        out = agent.invoke(
            _turn_input(user_query),
            config=thread_config(cid),
            version="v2",
        )
        hitl = None
        interrupts = getattr(out, "interrupts", None) or ()
        if interrupts:
            value = getattr(interrupts[0], "value", None)
            if isinstance(value, dict):
                hitl = value
        if hitl is None:
            hitl = read_hitl_interrupt(cid)

        if hitl is not None:
            approval = _approval_from_hitl(hitl, cid)
            answer = _pending_approval_answer((approval or {}).get("summary") or "")
            touch_conversation(cid)
            _safe_finish_audit(
                audit_session, audit_token, status="approval_required", model_result=answer
            )
            audit_token = None
            result = {
                "query": user_query,
                "answer": answer,
                "steps": [],
                "humanCs": None,
                "conversationId": cid,
            }
            if approval:
                result["approvalRequired"] = approval
            return result

        messages = (getattr(out, "value", None) or out or {}).get("messages") or []
        _ingest_messages_for_audit(audit_session, messages)
        steps, answer = _messages_to_steps_answer(messages)
        answer, steps, human_cs = _attach_forced_human_cs(
            query=user_query,
            steps=steps,
            answer=answer,
        )
        touch_conversation(cid)
        _safe_finish_audit(audit_session, audit_token, status="done", model_result=answer)
        audit_token = None
        return {
            "query": user_query,
            "answer": answer,
            "steps": steps,
            "humanCs": human_cs,
            "conversationId": cid,
        }
    except GraphRecursionError as exc:
        msg = _public_exc_message(exc)
        _safe_finish_audit(audit_session, audit_token, status="error", model_result=msg)
        audit_token = None
        return {
            "query": user_query,
            "answer": msg,
            "steps": [],
            "humanCs": None,
            "conversationId": cid,
        }
    except Exception:
        _safe_finish_audit(audit_session, audit_token, status="error", model_result=None)
        audit_token = None
        raise
    finally:
        if audit_token is not None:
            _safe_finish_audit(audit_session, audit_token, status="error", model_result=None)
        if token is not None:
            reset_execution_context(token)
        if runtime_tokens is not None:
            reset_runtime(*runtime_tokens)


async def stream_agent_loop(
    query: str,
    conversation_id: Optional[str] = None,
    *,
    execution_ctx: ExecutionContext | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """异步流式执行 AgentLoop，逐步 yield 事件字典。"""
    cid = ensure_conversation(conversation_id)
    user_query = (query or "").strip()
    runtime_tokens = None
    token = None
    audit_session = None
    audit_token = None
    audit_status = "done"
    audit_answer: str | None = None
    try:
        yield {"type": "status", "content": "thinking", "conversationId": cid}

        base_ctx = _bind_ctx_trace(
            replace(
                resolve_execution_context(execution_ctx),
                user_query=user_query,
                conversation_id=cid,
            )
        )
        audit_session, audit_token = _start_turn_audit(base_ctx)
        agent = build_agent(base_ctx)
        runtime_tokens = bind_runtime(agent, cid)
        token = set_execution_context(base_ctx)

        steps: list[dict[str, Any]] = []
        answer_parts: list[str] = []
        human_cs_emitted = False

        blocked = _pending_hitl(cid)
        if blocked is not None:
            _hitl, approval, answer = blocked
            audit_status = "approval_required"
            audit_answer = answer
            yield {"type": "reset_answer"}
            yield {"type": "token", "content": answer}
            if approval:
                yield _approval_required_event(approval, cid)
            touch_conversation(cid)
            yield {
                "type": "done",
                "query": user_query,
                "answer": answer,
                "steps": steps,
                "humanCs": None,
                "conversationId": cid,
                **({"approvalRequired": approval} if approval else {}),
            }
            return

        try:
            async for event in agent.astream_events(
                _turn_input(user_query),
                config=thread_config(cid),
                version="v2",
            ):
                kind = event.get("event")
                name = event.get("name") or ""
                data = event.get("data") or {}

                if kind == "on_chat_model_end":
                    output = data.get("output")
                    if output is not None and audit_session is not None:
                        audit_session.add_model_message(output)

                if kind == "on_tool_start":
                    if answer_parts:
                        answer_parts.clear()
                        yield {"type": "reset_answer"}
                    tool_input = _serialize_tool_io(data.get("input"))
                    step = {"tool": name, "input": tool_input, "observation": None}
                    steps.append(step)
                    yield {"type": "tool_start", "tool": name, "input": tool_input}

                elif kind == "on_tool_end":
                    observation = data.get("output")
                    if hasattr(observation, "content"):
                        observation = observation.content
                    observation = _serialize_tool_io(observation)
                    for step in reversed(steps):
                        if step.get("tool") == name and step.get("observation") is None:
                            step["observation"] = observation
                            break
                    yield {"type": "tool_end", "tool": name, "observation": observation}
                    if name == "escalate_to_human_cs":
                        payload = observation if isinstance(observation, dict) else None
                        if isinstance(observation, str):
                            try:
                                parsed = json.loads(observation)
                                if isinstance(parsed, dict):
                                    payload = parsed
                            except Exception:
                                payload = None
                        payload = payload or build_human_cs_payload()
                        yield {"type": "human_cs", **payload}
                        human_cs_emitted = True

                elif kind == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    if _chunk_has_tool_calls(chunk):
                        continue
                    text = _extract_text(getattr(chunk, "content", None))
                    if not text:
                        continue
                    if audit_session is not None:
                        audit_session.mark_first_token()
                    answer_parts.append(text)
                    yield {"type": "token", "content": text}

            hitl = read_hitl_interrupt(cid)
            if hitl is not None:
                approval = _approval_from_hitl(hitl, cid)
                answer = _pending_approval_answer((approval or {}).get("summary") or "")
                audit_status = "approval_required"
                audit_answer = answer
                yield {"type": "reset_answer"}
                yield {"type": "token", "content": answer}
                if approval:
                    yield _approval_required_event(approval, cid)
                touch_conversation(cid)
                yield {
                    "type": "done",
                    "query": user_query,
                    "answer": answer,
                    "steps": steps,
                    "humanCs": None,
                    "conversationId": cid,
                    **({"approvalRequired": approval} if approval else {}),
                }
                return

            raw_answer = "".join(answer_parts)
            already_escalated = has_escalate_step(steps)
            answer, steps, human_cs = _attach_forced_human_cs(
                query=user_query,
                steps=steps,
                answer=raw_answer,
            )
            audit_answer = answer

            if human_cs and not already_escalated:
                if answer != raw_answer:
                    yield {"type": "reset_answer"}
                    yield {"type": "token", "content": answer}
                yield {
                    "type": "tool_start",
                    "tool": "escalate_to_human_cs",
                    "input": {"reason": human_cs.get("reason")},
                }
                yield {
                    "type": "tool_end",
                    "tool": "escalate_to_human_cs",
                    "observation": human_cs,
                }
                yield {"type": "human_cs", **human_cs}
                human_cs_emitted = True
            elif human_cs and not human_cs_emitted:
                yield {"type": "human_cs", **human_cs}

            touch_conversation(cid)
            yield {
                "type": "done",
                "query": user_query,
                "answer": answer,
                "steps": steps,
                "humanCs": human_cs,
                "conversationId": cid,
            }
        except Exception as exc:  # noqa: BLE001
            # interrupt 可能以控制流异常冒泡；优先读 checkpoint
            hitl = read_hitl_interrupt(cid)
            if hitl is not None:
                approval = _approval_from_hitl(hitl, cid)
                answer = _pending_approval_answer((approval or {}).get("summary") or "")
                audit_status = "approval_required"
                audit_answer = answer
                yield {"type": "reset_answer"}
                yield {"type": "token", "content": answer}
                if approval:
                    yield _approval_required_event(approval, cid)
                touch_conversation(cid)
                yield {
                    "type": "done",
                    "query": user_query,
                    "answer": answer,
                    "steps": steps,
                    "humanCs": None,
                    "conversationId": cid,
                    **({"approvalRequired": approval} if approval else {}),
                }
                return
            audit_status = "error"
            msg = _public_exc_message(exc)
            audit_answer = msg
            yield {"type": "error", "message": msg}
    finally:
        _safe_finish_audit(
            audit_session, audit_token, status=audit_status, model_result=audit_answer
        )
        try:
            if token is not None:
                reset_execution_context(token)
        except ValueError:
            pass
        try:
            if runtime_tokens is not None:
                reset_runtime(*runtime_tokens)
        except ValueError:
            pass


def resume_agent_after_decision(
    conversation_id: str,
    decision: str,
    *,
    execution_ctx: ExecutionContext | None = None,
) -> dict[str, Any]:
    """对挂起的 HITL interrupt 执行 approve/reject，并跑完剩余图。"""
    cid = ensure_conversation(conversation_id)
    action = (decision or "").strip().lower()
    if action not in {"approve", "reject"}:
        return {"error": {"code": 400, "message": "decision 必须是 approve 或 reject"}}

    runtime_tokens = None
    token = None
    audit_session = None
    audit_token = None
    try:
        hitl_probe_agent = build_agent()
        runtime_tokens = bind_runtime(hitl_probe_agent, cid)
        hitl = read_hitl_interrupt(cid)
        if hitl is None:
            return {"error": {"code": 404, "message": "当前会话没有待审批操作"}}

        actions = hitl.get("action_requests") or []
        first = actions[0] if actions and isinstance(actions[0], dict) else {}
        tool_args = first.get("args") if isinstance(first.get("args"), dict) else {}
        reason = str(tool_args.get("reason") or "")

        base_ctx = _bind_ctx_trace(
            replace(
                resolve_execution_context(execution_ctx),
                conversation_id=cid,
                user_query=reason or "[审批通过]",
            )
        )
        audit_session, audit_token = _start_turn_audit(base_ctx)
        agent = build_agent(base_ctx)
        reset_runtime(*runtime_tokens)
        runtime_tokens = bind_runtime(agent, cid)
        token = set_execution_context(base_ctx)

        if action == "reject":
            resume_payload: dict[str, Any] = {
                "decisions": [
                    {
                        "type": "reject",
                        "message": "用户拒绝执行该高风险操作，请勿重试同一工具调用。",
                    }
                ]
            }
        else:
            resume_payload = {"decisions": [{"type": "approve"}]}

        out = agent.invoke(
            Command(resume=resume_payload),
            config=thread_config(cid),
            version="v2",
        )
        # 仍挂起则视为异常
        if getattr(out, "interrupts", None) or read_hitl_interrupt(cid):
            _safe_finish_audit(
                audit_session, audit_token, status="error", model_result="审批后仍有未完成的中断"
            )
            audit_token = None
            return {"error": {"code": 409, "message": "审批后仍有未完成的中断"}}

        messages = (getattr(out, "value", None) or out or {}).get("messages") or []
        _ingest_messages_for_audit(audit_session, messages)
        steps, answer = _messages_to_steps_answer(messages)
        if action == "reject" and not (answer or "").strip():
            answer = "已取消该高风险操作，未执行。"
        touch_conversation(cid)
        _safe_finish_audit(audit_session, audit_token, status="done", model_result=answer)
        audit_token = None
        return {
            "decision": action,
            "query": f"[审批{'通过' if action == 'approve' else '拒绝'}]",
            "answer": answer,
            "steps": steps,
            "humanCs": None,
            "conversationId": cid,
            "requestId": cid,
        }
    except Exception:
        _safe_finish_audit(audit_session, audit_token, status="error", model_result=None)
        audit_token = None
        raise
    finally:
        if audit_token is not None:
            _safe_finish_audit(audit_session, audit_token, status="error", model_result=None)
        if token is not None:
            reset_execution_context(token)
        if runtime_tokens is not None:
            reset_runtime(*runtime_tokens)


def iter_sse(events: Iterator[dict[str, Any]]) -> Iterator[str]:
    """将事件字典序列化为简易 SSE 文本帧（不含 id，供旧 POST 流使用）。"""
    for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
