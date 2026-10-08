"""从 MCP list_tools 装配本地 ToolDefinition（description/schema 来自远端）。"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, Field, create_model

from app.core.agent.tools.governance import StrictArgs, StrictResult, ToolDefinition, ToolPolicy
from app.core.agent.tools.mcp_client import McpToolInfo, call_mcp_tool, list_mcp_tools

Postprocess = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """本地治理元数据：远端负责 description/schema，本地负责 policy/后处理。"""

    name: str
    policy: ToolPolicy
    postprocess: Postprocess | None = None


def parameters_model_from_json_schema(
    name: str,
    schema: dict[str, Any] | None,
) -> type[StrictArgs]:
    """将 MCP inputSchema 转为 StrictArgs 子类（含 minLength/minimum 等约束）。"""
    schema = schema or {"type": "object", "properties": {}}
    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        properties = {}
    required = {str(x) for x in (schema.get("required") or []) if str(x)}

    fields: dict[str, Any] = {}
    for prop_name, prop_schema in properties.items():
        key = str(prop_name)
        if not key.isidentifier():
            continue
        prop = prop_schema if isinstance(prop_schema, dict) else {}
        annotation, default = _field_from_prop(prop, required=key in required)
        fields[key] = (annotation, default)

    model_name = _safe_model_name(name, suffix="_Args")
    return create_model(model_name, __base__=StrictArgs, **fields)  # type: ignore[call-overload]


def result_model_from_json_schema(
    name: str,
    schema: dict[str, Any] | None,
) -> type[BaseModel]:
    """将 MCP outputSchema 转为宽松结果模型。

    以 StrictResult（extra=allow）为基类，兼容错误信封与本地 postprocess 增删字段；
    有 oneOf/anyOf 时不强拆联合类型，仅保留开放对象契约。
    """
    schema = schema or {}
    if any(k in schema for k in ("oneOf", "anyOf", "allOf")):
        return create_model(  # type: ignore[call-overload]
            _safe_model_name(name, suffix="_Result"),
            __base__=StrictResult,
            error=(Optional[dict[str, Any]], Field(default=None)),
        )

    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        properties = {}

    fields: dict[str, Any] = {
        "error": (Optional[dict[str, Any]], Field(default=None)),
    }
    for prop_name, prop_schema in properties.items():
        key = str(prop_name)
        if not key.isidentifier() or key == "error":
            continue
        prop = prop_schema if isinstance(prop_schema, dict) else {}
        annotation = _annotation_from_schema(prop)
        fields[key] = (Optional[annotation], Field(default=None))  # type: ignore[valid-type]

    return create_model(  # type: ignore[call-overload]
        _safe_model_name(name, suffix="_Result"),
        __base__=StrictResult,
        **fields,
    )


def assemble_mcp_tool_definitions(specs: list[ToolSpec]) -> list[ToolDefinition]:
    """按本地 ToolSpec 列表从 MCP 发现并装配 ToolDefinition；缺工具则启动失败。"""
    if not specs:
        return []

    discovered = {item.name: item for item in list_mcp_tools()}
    missing = [spec.name for spec in specs if spec.name not in discovered]
    if missing:
        raise RuntimeError(
            "MCP 未发现所需业务工具（请先启动 mcpserver）: " + ", ".join(missing)
        )

    definitions: list[ToolDefinition] = []
    for spec in specs:
        info = discovered[spec.name]
        parameters_model = parameters_model_from_json_schema(spec.name, info.input_schema)
        result_model = result_model_from_json_schema(spec.name, info.output_schema)
        handler = _make_handler(spec.name, spec.postprocess)
        definitions.append(
            ToolDefinition(
                name=spec.name,
                description=info.description or spec.name,
                parameters_model=parameters_model,
                result_model=result_model,
                policy=spec.policy,
                handler=handler,  # type: ignore[arg-type]
            )
        )
    return definitions


def _make_handler(
    tool_name: str,
    postprocess: Postprocess | None,
) -> Callable[[StrictArgs], dict[str, Any]]:
    def _handler(args: StrictArgs) -> dict[str, Any]:
        payload = call_mcp_tool(tool_name, args.model_dump(exclude_none=True))
        if postprocess is not None and isinstance(payload, dict):
            return postprocess(payload)
        return payload

    return _handler


def _field_from_prop(prop: dict[str, Any], *, required: bool) -> tuple[Any, Any]:
    annotation = _annotation_from_schema(prop)
    description = prop.get("description")
    default_present = "default" in prop
    default_value = prop.get("default") if default_present else None

    field_kwargs: dict[str, Any] = {}
    if description:
        field_kwargs["description"] = str(description)

    min_length = prop.get("minLength")
    if isinstance(min_length, int):
        field_kwargs["min_length"] = min_length
    max_length = prop.get("maxLength")
    if isinstance(max_length, int):
        field_kwargs["max_length"] = max_length

    minimum = prop.get("minimum")
    if isinstance(minimum, (int, float)):
        field_kwargs["ge"] = minimum
    exclusive_min = prop.get("exclusiveMinimum")
    if isinstance(exclusive_min, (int, float)):
        field_kwargs["gt"] = exclusive_min
    maximum = prop.get("maximum")
    if isinstance(maximum, (int, float)):
        field_kwargs["le"] = maximum
    exclusive_max = prop.get("exclusiveMaximum")
    if isinstance(exclusive_max, (int, float)):
        field_kwargs["lt"] = exclusive_max

    if required and not default_present:
        return annotation, Field(..., **field_kwargs)

    # optional / has default
    if not required:
        annotation = Optional[annotation]  # type: ignore[assignment]
    if default_present:
        return annotation, Field(default=default_value, **field_kwargs)
    return annotation, Field(default=None, **field_kwargs)


def _annotation_from_schema(prop: dict[str, Any]) -> Any:
    type_name = prop.get("type")
    if isinstance(type_name, list):
        non_null = [t for t in type_name if t != "null"]
        type_name = non_null[0] if non_null else "string"

    if type_name == "string":
        return str
    if type_name == "integer":
        return int
    if type_name == "number":
        return float
    if type_name == "boolean":
        return bool
    if type_name == "array":
        return list[Any]
    if type_name == "object":
        return dict[str, Any]
    if "anyOf" in prop or "oneOf" in prop:
        return Any
    return Any


def _safe_model_name(tool_name: str, *, suffix: str = "_Args") -> str:
    cleaned = re.sub(r"[^0-9a-zA-Z_]", "_", tool_name)
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"Tool_{cleaned}"
    return f"{cleaned}{suffix}"
