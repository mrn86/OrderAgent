"""路由侧 A2A Client：派发 DispatchEnvelope，解析 report / approval_required。"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.helpers import get_data_parts, new_data_message
from a2a.types.a2a_pb2 import (
    Role,
    SendMessageConfiguration,
    SendMessageRequest,
    TaskState,
)

from app.core.agent.a2a_card import expert_base_url
from app.core.agent.protocol import DispatchEnvelope
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="a2a-dispatch")


def _run_async(coro):  # type: ignore[no-untyped-def]
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    future = _executor.submit(asyncio.run, coro)
    return future.result()


def _artifact_payloads(task) -> list[tuple[str, dict[str, Any]]]:  # type: ignore[no-untyped-def]
    out: list[tuple[str, dict[str, Any]]] = []
    for art in task.artifacts:
        name = art.name or ""
        for data in get_data_parts(art.parts):
            if isinstance(data, dict):
                out.append((name, data))
    return out


def _parse_task_result(task) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    state = task.status.state
    artifacts = _artifact_payloads(task)
    for name, data in artifacts:
        if name == "approval_required" or data.get("requestId") or data.get("request_id"):
            return {"type": "approval_required", "payload": data}
        if name == "report" or "conclusion" in data:
            return {"type": "report", "payload": data}
        if name == "failed":
            return {
                "type": "failed",
                "payload": {"message": str(data.get("message") or "专家任务失败")},
            }
    if state == TaskState.TASK_STATE_FAILED:
        msg = ""
        if task.status.HasField("message"):
            from a2a.helpers import get_message_text

            msg = get_message_text(task.status.message)
        return {"type": "failed", "payload": {"message": msg or "专家任务失败"}}
    return {"type": "failed", "payload": {"message": "专家未返回可解析报告"}}


async def send_dispatch_async(envelope: DispatchEnvelope) -> dict[str, Any]:
    base = expert_base_url(expert=envelope.expert)
    timeout_s = max(5.0, float(envelope.timeout_ms or get_settings().expert_task_timeout_ms) / 1000.0)
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=10.0)) as http:
        factory = ClientFactory(
            ClientConfig(
                streaming=False,
                httpx_client=http,
                supported_protocol_bindings=["JSONRPC"],
            )
        )
        client = await factory.create_from_url(base)
        # 不传 message.task_id：A2A 会要求该 Task 已存在；业务 task_id 在 data payload 内。
        message = new_data_message(
            envelope.model_dump(mode="json"),
            media_type="application/json",
            context_id=envelope.conversation_id,
            role=Role.ROLE_USER,
        )
        request = SendMessageRequest(
            message=message,
            configuration=SendMessageConfiguration(return_immediately=False),
        )
        last_task = None
        async for event in client.send_message(request):
            if event.HasField("task"):
                last_task = event.task
            elif event.HasField("status_update") and last_task is not None:
                last_task.status.CopyFrom(event.status_update.status)
            elif event.HasField("artifact_update") and last_task is not None:
                # 非流式通常直接给完整 Task；流式时拼 artifact
                art = event.artifact_update.artifact
                # 替换同名 artifact
                replaced = False
                for i, existing in enumerate(last_task.artifacts):
                    if existing.artifact_id == art.artifact_id or (
                        existing.name and existing.name == art.name
                    ):
                        last_task.artifacts[i].CopyFrom(art)
                        replaced = True
                        break
                if not replaced:
                    last_task.artifacts.append(art)
        if last_task is None:
            return {"type": "failed", "payload": {"message": "A2A 无任务响应"}}
        return _parse_task_result(last_task)


def send_dispatch(envelope: DispatchEnvelope) -> dict[str, Any]:
    try:
        return _run_async(send_dispatch_async(envelope))
    except Exception as exc:  # noqa: BLE001
        logger.exception("a2a dispatch failed expert=%s task=%s", envelope.expert, envelope.task_id)
        return {"type": "failed", "payload": {"message": f"A2A 派发失败: {exc}"}}


async def resume_via_http_async(expert: str, task_id: str, action: str) -> dict[str, Any]:
    base = expert_base_url(expert=expert)
    timeout_s = max(5.0, float(get_settings().expert_task_timeout_ms) / 1000.0)
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=10.0)) as http:
        resp = await http.post(
            f"{base}/v1/a2a/resume",
            json={"taskId": task_id, "action": action},
        )
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            return {"type": "failed", "payload": {"message": "resume 响应无效"}}
        if body.get("type") in {"report", "failed", "approval_required"}:
            return body
        if "report" in body and isinstance(body["report"], dict):
            return {"type": "report", "payload": body["report"]}
        if body.get("error"):
            err = body["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            return {"type": "failed", "payload": {"message": str(msg)}}
        return {"type": "failed", "payload": {"message": "resume 未返回报告"}}


def resume_via_http(expert: str, task_id: str, action: str) -> dict[str, Any]:
    try:
        return _run_async(resume_via_http_async(expert, task_id, action))
    except Exception as exc:  # noqa: BLE001
        logger.exception("a2a resume failed expert=%s task=%s", expert, task_id)
        return {"type": "failed", "payload": {"message": f"A2A 恢复失败: {exc}"}}
