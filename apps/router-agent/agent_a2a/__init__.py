"""路由进程的 A2A Client。"""

from agent_a2a.client import resume_via_http, send_dispatch

__all__ = ["resume_via_http", "send_dispatch"]


def install_router_a2a() -> None:
    """把本进程的 A2A Client 接到派发入口。"""
    from app.core.agent.dispatch import bind_a2a_client

    bind_a2a_client(send=send_dispatch, resume=resume_via_http)
