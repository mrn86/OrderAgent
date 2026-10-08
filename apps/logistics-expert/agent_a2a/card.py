"""本专家的 AgentCard。"""

from __future__ import annotations

from google.protobuf.json_format import ParseDict

from a2a.types.a2a_pb2 import AgentCard
from a2a.utils.constants import PROTOCOL_VERSION_CURRENT

from app.core.agent.profiles import AgentProfile, current_profile
from app.core.config import get_settings


def expert_base_url(*, expert: str | None = None, profile: AgentProfile | None = None) -> str:
    settings = get_settings()
    if settings.expert_a2a_public_url.strip():
        return settings.expert_a2a_public_url.rstrip("/")
    name = expert or (profile.expert_name if profile else None) or current_profile().expert_name or "order"
    return settings.expert_a2a_url(name)


def build_expert_agent_card(profile: AgentProfile | None = None) -> AgentCard:
    profile = profile or current_profile()
    base = expert_base_url(profile=profile)
    skill_id = profile.expert_name or profile.role
    payload = {
        "name": profile.agent_name or profile.agent_id,
        "description": f"{profile.agent_name}（A2A 专家）",
        "version": "1.5.0",
        "capabilities": {"streaming": True},
        "defaultInputModes": ["application/json", "text/plain"],
        "defaultOutputModes": ["application/json", "text/plain"],
        "skills": [
            {
                "id": skill_id,
                "name": profile.agent_name or skill_id,
                "description": f"处理 {skill_id} 域任务并回传 ExpertReport",
                "tags": [skill_id, "expert"],
            }
        ],
        "supportedInterfaces": [
            {
                "url": f"{base}/",
                "protocolBinding": "JSONRPC",
                "protocolVersion": PROTOCOL_VERSION_CURRENT,
            }
        ],
    }
    return ParseDict(payload, AgentCard())
