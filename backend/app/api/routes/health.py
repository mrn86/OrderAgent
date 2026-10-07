from fastapi import APIRouter

from app.core.database.db import ping_db
from app.core.database.redis_client import ping_redis
from app.core.response import ok

router = APIRouter()


@router.get("/health")
def health():
    return ok(
        {
            "status": "up",
            "fakeData": True,
            "postgres": ping_db(),
            "redis": ping_redis(),
        }
    )
