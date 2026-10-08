"""跨域共用的错误信封与校验辅助。"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T", bound=BaseModel)


class StrictModel(BaseModel):
    """入参：拒绝未声明字段。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OpenModel(BaseModel):
    """出参：允许业务扩展字段（详情类接口嵌套深）。"""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)


class ErrorInfo(StrictModel):
    code: int
    message: str = Field(..., min_length=1)


class ToolErrorResult(StrictModel):
    error: ErrorInfo


def as_tool_result(success_cls: type[T], data: dict[str, Any]) -> T | ToolErrorResult:
    """将 service dict 校验为成功模型或错误信封。"""
    if isinstance(data, dict) and "error" in data:
        return ToolErrorResult.model_validate(data)
    return success_cls.model_validate(data)
