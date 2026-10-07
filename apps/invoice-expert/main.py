"""发票专家进程。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("AGENT_ROLE", "invoice")
os.environ.setdefault("AGENT_ID", "invoice-expert")
os.environ.setdefault("AGENT_NAME", "发票专家")

_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.expert_app import app, create_expert_app  # noqa: E402

__all__ = ["app", "create_expert_app"]
