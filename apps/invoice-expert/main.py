"""发票专家进程。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 强制本进程身份，避免父 shell / 共享 .env 残留 AGENT_* 污染多专家启动
os.environ["AGENT_ROLE"] = "invoice"
os.environ["AGENT_ID"] = "invoice-expert"
os.environ["AGENT_NAME"] = "发票专家"

_APP = Path(__file__).resolve().parent
_ROOT = _APP.parents[1]
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from access import register_invoice_access  # noqa: E402
from prompts import register_invoice_prompts  # noqa: E402
from tools import register_invoice_tools  # noqa: E402

register_invoice_access()
register_invoice_prompts()
register_invoice_tools()

from agent_a2a import ParkedExpertTask, install_expert_a2a, park_task, take_parked  # noqa: E402
from app.core.agent.expert_worker import bind_task_registry  # noqa: E402

bind_task_registry(park=park_task, take=take_parked, parked_type=ParkedExpertTask)

from app.expert_app import app, create_expert_app  # noqa: E402

install_expert_a2a(app)

__all__ = ["app", "create_expert_app"]
