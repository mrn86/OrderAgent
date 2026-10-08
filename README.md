# Order Agent

订单智能助手 monorepo：路由 + 订单/物流/发票专家（独立进程，A2A 派发）+ 业务 MCP Server。

| 目录 | 说明 |
|------|------|
| [`packages/agent-common`](./packages/agent-common) | 共享库（`backend/app`） |
| [`mcpserver/`](./mcpserver) | 业务 MCP Server + 假数据与业务 service |
| [`apps/router-agent`](./apps/router-agent) | 对用户 HTTP/SSE、编排与复核 |
| [`apps/order-expert`](./apps/order-expert) | 订单/售后/退款专家（A2A Server，业务工具经 MCP） |
| [`apps/logistics-expert`](./apps/logistics-expert) | 物流轨迹/运单专家（A2A Server，业务工具经 MCP） |
| [`apps/invoice-expert`](./apps/invoice-expert) | 发票专家（A2A Server，业务工具经 MCP） |
| [`web/`](./web) | Vue 3 对话前端（只打路由网关） |

专家互不通信；路由经 A2A（JSON-RPC）派发并回收 ExpertReport。专家启动时经 MCP `list_tools` 发现并装配业务工具，调用走 MCP。Redis 仍用于 SSE / 任务 meta / HITL 关联。

## 快速启动

五个进程（**必须先启动 MCP**，专家启动依赖发现；MCP 未就绪会启动失败）：

```bash
# 0. 业务 MCP（专家工具依赖；默认 http://127.0.0.1:8010/mcp）
cd mcpserver
python main.py

# 1. 路由（工具在 apps/router-agent 内创建）
cd ../apps/router-agent
uvicorn main:app --host 127.0.0.1 --port 8000

# 2. 订单专家（工具在 apps/order-expert 内创建）
cd ../order-expert
uvicorn main:app --host 127.0.0.1 --port 8001

# 3. 物流专家（工具在 apps/logistics-expert 内创建）
cd ../logistics-expert
uvicorn main:app --host 127.0.0.1 --port 8003

# 4. 发票专家（工具在 apps/invoice-expert 内创建）
cd ../invoice-expert
uvicorn main:app --host 127.0.0.1 --port 8002
```

可选：`MCP_SERVER_URL`（专家侧，默认 `http://127.0.0.1:8010/mcp`）。

前端：`cd web && npm run dev` → http://127.0.0.1:5173
