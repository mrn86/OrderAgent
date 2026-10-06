"""从 LLM 响应元数据解析真实模型 / fallback / 限流标记。"""

from __future__ import annotations

from typing import Any

from app.gateway.llm_router import FALLBACK_GROUP, PRIMARY_GROUP, get_litellm_router


def _model_id_to_litellm_model(model_id: str | None) -> str | None:
    if not model_id:
        return None
    try:
        router = get_litellm_router()
        for entry in router.model_list or []:
            if not isinstance(entry, dict):
                continue
            # LiteLLM may store model_info.model_id
            info = entry.get("model_info") or {}
            if str(info.get("id") or info.get("model_id") or "") == str(model_id):
                params = entry.get("litellm_params") or {}
                model = params.get("model")
                return str(model) if model else None
            if str(entry.get("model_name") or "") == str(model_id):
                params = entry.get("litellm_params") or {}
                model = params.get("model")
                return str(model) if model else None
    except Exception:  # noqa: BLE001
        return None
    return None


def _group_for_model_id(model_id: str | None) -> str | None:
    if not model_id:
        return None
    try:
        router = get_litellm_router()
        for entry in router.model_list or []:
            if not isinstance(entry, dict):
                continue
            info = entry.get("model_info") or {}
            if str(info.get("id") or info.get("model_id") or "") == str(model_id):
                return str(entry.get("model_name") or "") or None
    except Exception:  # noqa: BLE001
        return None
    return None


def parse_model_call_meta(
    message: Any,
    *,
    round_index: int,
    rate_limited: bool = False,
) -> dict[str, Any]:
    """从 AIMessage / chunk 的 response_metadata 解析一次模型调用。"""
    meta = getattr(message, "response_metadata", None) or {}
    if not isinstance(meta, dict):
        meta = {}

    requested_group = str(meta.get("model_name") or PRIMARY_GROUP)
    model_id = meta.get("model_id")
    model_id_str = str(model_id) if model_id is not None else None

    resolved = (
        meta.get("model")
        or _model_id_to_litellm_model(model_id_str)
        or meta.get("ls_model_name")
        or requested_group
    )
    resolved_model = str(resolved)

    group_from_id = _group_for_model_id(model_id_str)
    fallback = bool(
        group_from_id == FALLBACK_GROUP
        or requested_group == FALLBACK_GROUP
        or FALLBACK_GROUP in resolved_model
        or int(meta.get("attempted_fallbacks") or 0) > 0
    )

    return {
        "round": round_index,
        "requested_group": requested_group or PRIMARY_GROUP,
        "resolved_model": resolved_model,
        "model_id": model_id_str,
        "fallback": fallback,
        "rate_limited": bool(rate_limited),
    }


def extract_usage(message: Any) -> dict[str, int] | None:
    usage = getattr(message, "usage_metadata", None)
    if not isinstance(usage, dict):
        return None
    inp = usage.get("input_tokens")
    out = usage.get("output_tokens")
    total = usage.get("total_tokens")
    if inp is None and out is None and total is None:
        return None
    inp_i = int(inp or 0)
    out_i = int(out or 0)
    total_i = int(total) if total is not None else inp_i + out_i
    return {"input": inp_i, "output": out_i, "total": total_i}
