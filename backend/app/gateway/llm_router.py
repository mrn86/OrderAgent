"""LiteLLM Router：模型 fallback + RPM/TPM 限流（网关侧 LLM 出口）。"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_litellm import ChatLiteLLMRouter
from litellm import Router
from litellm.types.router import RetryPolicy

from app.core.config import get_settings

# 对外统一模型组名；Agent / 分类器都走这一组
PRIMARY_GROUP = "order-agent"
FALLBACK_GROUP = "order-agent-fallback"


def _deployment(
    *,
    model_name: str,
    litellm_model: str,
    api_key: str,
    api_base: str | None,
    rpm: int,
    tpm: int,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "model": litellm_model,
        "api_key": api_key,
        "rpm": rpm,
        "tpm": tpm,
    }
    if api_base:
        params["api_base"] = api_base
    return {"model_name": model_name, "litellm_params": params}


@lru_cache
def get_litellm_router() -> Router:
    """构建带 fallback 与调用限流的 LiteLLM Router。"""
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")

    # LiteLLM DeepSeek 模型名：deepseek/<model>
    primary_model = settings.litellm_primary_model
    fallback_model = settings.litellm_fallback_model or primary_model

    model_list: list[dict[str, Any]] = [
        _deployment(
            model_name=PRIMARY_GROUP,
            litellm_model=primary_model,
            api_key=settings.deepseek_api_key,
            api_base=settings.deepseek_base_url or None,
            rpm=settings.litellm_rpm,
            tpm=settings.litellm_tpm,
        ),
        _deployment(
            model_name=FALLBACK_GROUP,
            litellm_model=fallback_model,
            api_key=settings.litellm_fallback_api_key or settings.deepseek_api_key,
            api_base=settings.litellm_fallback_api_base or settings.deepseek_base_url or None,
            rpm=settings.litellm_fallback_rpm or settings.litellm_rpm,
            tpm=settings.litellm_fallback_tpm or settings.litellm_tpm,
        ),
    ]

    # OpenAI 可选第二 fallback（配置了 OPENAI_API_KEY 时启用）
    if settings.openai_api_key and settings.litellm_openai_fallback_model:
        model_list.append(
            _deployment(
                model_name=FALLBACK_GROUP,
                litellm_model=settings.litellm_openai_fallback_model,
                api_key=settings.openai_api_key,
                api_base=settings.openai_base_url or None,
                rpm=settings.litellm_fallback_rpm or settings.litellm_rpm,
                tpm=settings.litellm_fallback_tpm or settings.litellm_tpm,
            )
        )

    retries = max(0, int(settings.litellm_num_retries))
    rate_limit_retries = max(retries, int(settings.litellm_rate_limit_retries))
    return Router(
        model_list=model_list,
        fallbacks=[{PRIMARY_GROUP: [FALLBACK_GROUP]}],
        num_retries=retries,
        timeout=settings.litellm_timeout,
        # 有限次重试 + 指数退避（尊重上游 Retry-After；否则 2^n * INITIAL_RETRY_DELAY）
        retry_after=max(0, int(settings.litellm_retry_after)),
        retry_policy=RetryPolicy(
            RateLimitErrorRetries=rate_limit_retries,
            TimeoutErrorRetries=retries,
            InternalServerErrorRetries=retries,
            ServiceUnavailableErrorRetries=retries,
        ),
        set_verbose=False,
    )


def build_llm(*, streaming: bool = True, temperature: float = 0.2) -> ChatLiteLLMRouter:
    """供 Agent / 分类器使用的 Chat 模型（经 LiteLLM Router）。"""
    router = get_litellm_router()
    return ChatLiteLLMRouter(
        router=router,
        model=PRIMARY_GROUP,
        temperature=temperature,
        streaming=streaming,
    )
