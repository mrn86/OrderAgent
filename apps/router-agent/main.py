"""路由 Agent 进程（对用户 HTTP/SSE）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 强制本进程身份，避免父 shell / 共享 .env 残留 AGENT_* 污染多专家启动
os.environ["AGENT_ROLE"] = "router"
os.environ["AGENT_ID"] = "router-agent"
os.environ["AGENT_NAME"] = "路由智能助手"

_APP = Path(__file__).resolve().parent
_ROOT = _APP.parents[1]
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.domains.ecommerce import register_ecommerce_domain  # noqa: E402
from access import register_router_access  # noqa: E402
from agent_a2a import install_router_a2a  # noqa: E402
from prompts import register_router_prompts  # noqa: E402
from tools import register_router_tools  # noqa: E402

register_ecommerce_domain()
register_router_access()
install_router_a2a()
register_router_prompts()
register_router_tools()

from app.main import app, create_app  # noqa: E402

__all__ = ["app", "create_app"]
