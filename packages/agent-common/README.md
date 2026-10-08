# agent-common

共享库：`backend/app`（loop、工具治理、MCP 客户端、审计、业务 service）。A2A 传输在各 app 内；业务工具经根目录 `mcpserver`。

```bash
pip install -e packages/agent-common
```

角色由环境变量 `AGENT_ROLE=router|order|logistics|invoice` 选择。
