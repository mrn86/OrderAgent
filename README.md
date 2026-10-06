# Order Agent

订单智能助手 monorepo，包含两个独立子项目：

| 目录 | 说明 |
|------|------|
| [`backend/`](./backend) | LangChain Agent + FastAPI 后端 |
| [`web/`](./web) | Vue 3 对话前端 |

## 快速启动

```bash
# 后端（仓库根目录）
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt   # 首次
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端（另开终端，仓库根目录）
cd web
npm install                       # 首次
npm run dev
```

浏览器打开：http://127.0.0.1:5173
