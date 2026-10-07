from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "order-agent"
    app_env: str = "dev"
    api_prefix: str = "/v1"
    access_token: str = "test-token"

    # 审计：Agent 标识与 token/结果落盘策略
    agent_id: str = "router-agent"
    agent_name: str = "路由智能助手"
    # router | order | invoice — 三进程各自设置
    agent_role: str = "router"
    task_ttl_seconds: int = 1800
    expert_task_timeout_ms: int = 120000
    dispatch_stream_maxlen: int = 10000
    task_pending_idle_ms: int = 60000
    audit_token_budget: int = 100000
    audit_model_result_max_chars: int = 2000

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # LiteLLM：主模型 / fallback / 调用限流
    litellm_primary_model: str = "deepseek/deepseek-chat"
    litellm_fallback_model: str = "deepseek/deepseek-chat"
    litellm_fallback_api_key: str = ""
    litellm_fallback_api_base: str = ""
    litellm_rpm: int = 60
    litellm_tpm: int = 100000
    litellm_fallback_rpm: int = 0
    litellm_fallback_tpm: int = 0
    litellm_num_retries: int = 3
    # 上游限流（429）优先多试几次；指数退避由 LiteLLM _calculate_retry_after 执行
    litellm_rate_limit_retries: int = 4
    litellm_retry_after: int = 1  # 重试前最小等待秒数
    litellm_timeout: float = 60.0

    # 可选 OpenAI fallback
    openai_api_key: str = ""
    openai_base_url: str = ""
    litellm_openai_fallback_model: str = "openai/gpt-4o-mini"

    # 网关 HTTP 限流（每 access token 每分钟）
    gateway_rate_limit_per_minute: int = 30

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/order_agent"
    redis_url: str = "redis://localhost:6379/0"
    use_fake_data: bool = True

    human_cs_url: str = "http://www.baidu.com"

    # 上下文压缩：估窗阈值；keep 按用户轮而非消息条数
    context_compress_max_messages: int = 40
    context_compress_max_tokens: int = 8000
    context_keep_recent_turns: int = 3
    context_tool_result_max_chars: int = 4000
    # 仅作记录；真正上限由 create_agent 绑定的 9999，停机靠 ToolLoopGuard
    agent_recursion_limit: int = 9999
    # 同一用户轮内最多几轮 tool_calls；达到后去掉 tool_calls 并结束图
    agent_max_tool_rounds: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
