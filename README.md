# Order Agent

订单智能助手 monorepo：路由 + 订单/物流/发票专家（独立进程，A2A 派发）。

| 目录 | 说明 |
|------|------|
| [`packages/agent-common`](./packages/agent-common) | 共享库（`backend/app`） |
| [`apps/router-agent`](./apps/router-agent) | 对用户 HTTP/SSE、编排与复核 |
| [`apps/order-expert`](./apps/order-expert) | 订单/售后/退款专家（A2A Server） |
| [`apps/logistics-expert`](./apps/logistics-expert) | 物流轨迹/运单专家（A2A Server） |
| [`apps/invoice-expert`](./apps/invoice-expert) | 发票专家（A2A Server） |
| [`web/`](./web) | Vue 3 对话前端（只打路由网关） |

专家互不通信；路由经 A2A（JSON-RPC）派发并回收 ExpertReport。Redis 仍用于 SSE / 任务 meta / HITL 关联。

## 快速启动

四个进程：

```bash
# 1. 路由
cd backend
# Windows: .venv\Scripts\activate
set AGENT_ROLE=router
set AGENT_ID=router-agent
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. 订单专家
set AGENT_ROLE=order
set AGENT_ID=order-expert
uvicorn app.expert_app:app --host 127.0.0.1 --port 8001

# 3. 物流专家
set AGENT_ROLE=logistics
set AGENT_ID=logistics-expert
uvicorn app.expert_app:app --host 127.0.0.1 --port 8003

# 4. 发票专家
set AGENT_ROLE=invoice
set AGENT_ID=invoice-expert
uvicorn app.expert_app:app --host 127.0.0.1 --port 8002
```

前端：`cd web && npm run dev` → http://127.0.0.1:5173
