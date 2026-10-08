# Order Agent Backend

LangChain 多 Agent：路由 + 订单/物流/发票专家，共享本目录 `app` 包；业务工具经根目录 `mcpserver`（MCP）。

- MCP：`mcpserver` → `python main.py`（默认 `http://127.0.0.1:8010/mcp`）
- 路由：`apps/router-agent` → `uvicorn main:app`（派发工具在该进程内安装）
- 订单专家：`apps/order-expert` → `uvicorn main:app`（业务 handler 经 MCP）
- 物流专家：`apps/logistics-expert` → `uvicorn main:app`（业务 handler 经 MCP）
- 发票专家：`apps/invoice-expert` → `uvicorn main:app`（业务 handler 经 MCP）

进程间派发走 A2A（各 app 自己的 Client/Server）；HITL 经专家 `POST /v1/a2a/resume`。
专家启动时 MCP `list_tools` 发现并装配业务工具，调用走 MCP；Redis 仅保留 SSE / 任务 meta / conversation↔task HITL 映射。


分层：

- `app/api`：FastAPI 路由（经 `app.service` → MCP）
- `app/service`：业务 MCP 适配器（假数据在 `mcpserver/data`）
- `app/core`：配置、Redis/PG、AgentLoop/Tools（含 `mcp_client`）

配套前端：`../web`（Vue3）。

> 业务假数据在 `../mcpserver/data/fake_data.py`；访问前须先启动 MCP。  
> 默认 `USE_FAKE_DATA=true` 仍控制 DB/Redis 旁路行为。  

> **系统提示词**默认内容在各 `apps/*/prompts`；存储层仍为 `app/gateway/prompts`（PostgreSQL `system_prompts`，库不可用时回退内存）。各进程启动时只种子自己的 key。  
> 若本机尚无库：`python scripts/create_db.py`

## 1. 安装

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

配置见 `.env`（请勿提交到公开仓库）。

## 2. 启动 API

先启动 MCP（专家依赖），再启动路由：

```bash
cd ../mcpserver
python main.py

cd ../apps/router-agent
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

健康检查：

```bash
curl -H "Authorization: Bearer test-token" http://127.0.0.1:8000/v1/health
```

## 2.1 启动 Web 前端

```bash
cd web
npm install
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`。

## 3. 接口示例

鉴权 Header 默认：`Authorization: Bearer test-token`

```bash
curl -H "Authorization: Bearer test-token" "http://127.0.0.1:8000/v1/orders?orderNo=2026100210000002"
curl -H "Authorization: Bearer test-token" http://127.0.0.1:8000/v1/orders/O20261002002
curl -H "Authorization: Bearer test-token" http://127.0.0.1:8000/v1/logistics/by-order-no/2026100210000002
```

Agent 对话请使用 Web 前端，或：

```bash
curl -X POST http://127.0.0.1:8000/v1/agent/chat \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"帮我查订单号 2026100210000002 的物流\"}"
```

## 4. 假数据主键

| 类型 | 值 |
|------|----|
| 订单号（运输中 + 退货中） | `2026100210000002` / `O20261002002` |
| 售后单（退货退款进行中） | `AS20260925001` |
| 订单号（已完成 + 仅退款成功） | `2026091508765432` / `O20260915008` |
| 售后单 / 退款单 | `AS20260918008` / `RF20260929001` |
| 运单号 | `SF1234567890` |
| 发票 | `INV20260929001` |
