# Order Agent Web

独立的 Vue 3 前端，对接路由 Agent（`apps/router-agent`）对话接口。

## 启动

```bash
# 先启动路由（及订单/物流/发票专家，见仓库根 README）
cd apps/router-agent
uvicorn main:app --host 127.0.0.1 --port 8000

# 再启动前端
cd ../../web
npm install
npm run dev
```

浏览器：http://127.0.0.1:5173  

开发环境通过 Vite 代理把 `/v1` 转发到 `http://127.0.0.1:8000`。

## 环境变量

复制 `.env.example` 为 `.env`（可选）：

| 变量 | 说明 | 默认 |
|------|------|------|
| `VITE_API_BASE` | API 前缀 | `/v1` |
| `VITE_ACCESS_TOKEN` | 鉴权 Token | `test-token` |
| `VITE_HUMAN_CS_URL` | 人工客服链接 | `http://www.baidu.com` |

## 接口

- `POST /v1/agent/chat/stream/sessions`：创建流式会话
- `GET /v1/agent/chat/stream?sessionId=`：EventSource 订阅
