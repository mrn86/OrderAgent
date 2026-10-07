# agent-common

四进程共享库：`backend/app`（loop、工具治理、审计、业务 service）。A2A 传输在各 app 内。

```bash
pip install -e packages/agent-common
```

角色由环境变量 `AGENT_ROLE=router|order|logistics|invoice` 选择。
