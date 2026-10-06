from fastapi import APIRouter

from app.api.routes import after_sales, health, invoices, logistics, orders, refunds
from app.gateway.routes import router as agent_router
from app.gateway.routes import sse_router as agent_sse_router


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(health.router, tags=["health"])
    router.include_router(orders.router, tags=["orders"])
    router.include_router(logistics.router, tags=["logistics"])
    router.include_router(after_sales.router, tags=["after-sales"])
    router.include_router(refunds.router, tags=["refunds"])
    router.include_router(invoices.router, tags=["invoices"])
    router.include_router(agent_router, tags=["agent"])
    router.include_router(agent_sse_router, tags=["agent"])
    return router
