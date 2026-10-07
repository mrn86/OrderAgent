"""路由 Agent 进程（对用户 HTTP/SSE）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("AGENT_ROLE", "router")
os.environ.setdefault("AGENT_ID", "router-agent")
os.environ.setdefault("AGENT_NAME", "路由智能助手")

_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.main import app, create_app  # noqa: E402

__all__ = ["app", "create_app"]
