"""将 mcpserver/ 挂到 sys.path，供 data / service / tools 本地 import。"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent

text = str(_HERE)
if text not in sys.path:
    sys.path.insert(0, text)
