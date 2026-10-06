"""LLM 工厂：经网关 LiteLLM Router（fallback + RPM/TPM）。"""

from app.gateway.llm_router import build_llm

__all__ = ["build_llm"]
