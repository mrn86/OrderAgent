# Order Agent Backend

LangChain Agent + FastAPI + PostgreSQL + Redis + Python 后端。

分层：

- `app/api`：FastAPI 路由
- `app/service`：业务逻辑
- `app/core`：配置、假数据、Redis/PG、AgentLoop/Tools

配套前端：`../web`（Vue3）。

> 默认 `USE_FAKE_DATA=true`，业务查询可不依赖真实库。  
> **系统提示词**由网关 `app/gateway/prompts` 管理，存 PostgreSQL 表 `system_prompts`（启动时自动建表/种子）；库不可用时回退内存。  
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

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
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
curl -H "Authorization: Bearer test-token" "http://127.0.0.1:8000/v1/orders?orderNo=2026092012345678"
curl -H "Authorization: Bearer test-token" http://127.0.0.1:8000/v1/orders/O20260920001
curl -H "Authorization: Bearer test-token" http://127.0.0.1:8000/v1/logistics/by-order-no/2026092012345678
```

Agent 对话请使用 Web 前端，或：

```bash
curl -X POST http://127.0.0.1:8000/v1/agent/chat \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"帮我查订单号 2026092012345678 的物流\"}"
```

## 4. 假数据主键

| 类型 | 值 |
|------|----|
| 订单号 | `2026092012345678` |
| 订单 ID | `O20260920001` |
| 运单号 | `SF1234567890` |
| 售后单 | `AS20260925001` |
| 退款单 | `RF20260929001` |
| 发票 | `INV20260929001` |
