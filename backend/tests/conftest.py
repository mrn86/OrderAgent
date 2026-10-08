"""测试默认安装电商域钩子。"""

from __future__ import annotations

import pytest

from app.domains.ecommerce import ensure_ecommerce_domain


@pytest.fixture(autouse=True)
def _ecommerce_domain() -> None:
    ensure_ecommerce_domain()
