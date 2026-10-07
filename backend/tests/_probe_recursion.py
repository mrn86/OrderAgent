from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from app.core.context.compression import ContextCompressionMiddleware
from app.core.agent.graph_runtime import OrderAgentState
from app.core.agent.loop_guard import ToolLoopGuardMiddleware


@tool
def query_orders() -> str:
    """list orders"""
    return '{"list":[{"orderId":"O1","orderNo":"1","statusText":"运输中"}],"total":1}'


class AlwaysToolModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "always-tool"

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ARG002
        n = sum(1 for m in messages if isinstance(m, AIMessage) and (m.tool_calls or []))
        ai = AIMessage(
            content=f"round{n}",
            tool_calls=[{"name": "query_orders", "args": {}, "id": f"c{n}", "type": "tool_call"}],
        )
        return ChatResult(generations=[ChatGeneration(message=ai)])


def node_names(agent) -> list[str]:
    compiled = getattr(agent, "bound", agent)
    return sorted(str(n) for n in compiled.get_graph().nodes)


def main() -> None:
    agent = create_agent(
        model=AlwaysToolModel(),
        tools=[query_orders],
        middleware=[ContextCompressionMiddleware(), ToolLoopGuardMiddleware()],
        state_schema=OrderAgentState,
        checkpointer=MemorySaver(),
    )
    print("nodes", len(node_names(agent)))
    for n in node_names(agent):
        print(" ", n)

    cfg = {"configurable": {"thread_id": "t1"}, "recursion_limit": 25}
    out = agent.invoke({"messages": [HumanMessage(content="查看全部订单")]}, config=cfg)
    msgs = (out.get("messages") if isinstance(out, dict) else out) or []
    print("invoke under limit=25: n_messages", len(msgs), [type(m).__name__ for m in msgs])
    last = msgs[-1]
    print(
        "last",
        type(last).__name__,
        "tool_calls",
        getattr(last, "tool_calls", None),
        "content",
        (getattr(last, "content", None) or "")[:120],
    )


if __name__ == "__main__":
    main()
