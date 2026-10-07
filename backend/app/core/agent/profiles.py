"""进程内 AgentProfile：角色元数据 / 白名单 / 权限由各 Agent 安装。"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings

_PROCESS_META: dict[str, str | None] | None = None
_PROCESS_TOOLS: frozenset[str] = frozenset()
_PROCESS_PERMISSIONS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class AgentProfile:
    role: str
    agent_id: str
    agent_name: str
    prompt_key: str
    tools: frozenset[str]
    permissions: frozenset[str]
    expert_name: str | None  # 专家进程填本域名；路由为 None


def expert_thread_id(conversation_id: str, agent_id: str, task_id: str) -> str:
    return f"{conversation_id}:{agent_id}:{task_id}"


def install_process_profile(
    *,
    role: str,
    prompt_key: str,
    expert_name: str | None = None,
    agent_id: str | None = None,
    agent_name: str | None = None,
    tools: frozenset[str] | set[str] | None = None,
    permissions: frozenset[str] | set[str] | None = None,
) -> None:
    """安装本进程角色元数据；可选同时写入白名单与权限。"""
    global _PROCESS_META, _PROCESS_TOOLS, _PROCESS_PERMISSIONS
    _PROCESS_META = {
        "role": role,
        "prompt_key": prompt_key,
        "expert_name": expert_name,
        "agent_id": agent_id or role,
        "agent_name": agent_name or role,
    }
    if tools is not None:
        _PROCESS_TOOLS = frozenset(tools)
    if permissions is not None:
        _PROCESS_PERMISSIONS = frozenset(permissions)


def install_process_access(
    *,
    tools: frozenset[str] | set[str],
    permissions: frozenset[str] | set[str],
) -> None:
    """更新本进程工具白名单与权限（可在 profile 安装前后调用）。"""
    global _PROCESS_TOOLS, _PROCESS_PERMISSIONS
    _PROCESS_TOOLS = frozenset(tools)
    _PROCESS_PERMISSIONS = frozenset(permissions)


def current_profile() -> AgentProfile:
    if _PROCESS_META is None:
        raise RuntimeError("AgentProfile 未安装：请在进程入口调用 install_process_profile")
    settings = get_settings()
    meta = _PROCESS_META
    # 进程入口 install_process_profile 为身份权威来源；settings 仅作缺省回退
    return AgentProfile(
        role=str(meta["role"] or "") or settings.agent_role,
        agent_id=str(meta["agent_id"] or "") or settings.agent_id,
        agent_name=str(meta["agent_name"] or "") or settings.agent_name,
        prompt_key=str(meta["prompt_key"] or ""),
        tools=_PROCESS_TOOLS,
        permissions=_PROCESS_PERMISSIONS,
        expert_name=meta["expert_name"],
    )
