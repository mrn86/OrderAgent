from __future__ import annotations

import time
import uuid
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    requestId: str = Field(default_factory=lambda: str(uuid.uuid4()))
    data: Optional[T] = None
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


def ok(data: Any = None, message: str = "ok") -> dict[str, Any]:
    return ApiResponse(code=0, message=message, data=data).model_dump()


def fail(code: int, message: str, data: Any = None) -> dict[str, Any]:
    return ApiResponse(code=code, message=message, data=data).model_dump()
