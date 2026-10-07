# agent-common

四进程共享库：`backend/app`（loop、工具治理、审计、A2A 派发、业务 service）。

```bash
pip install -e packages/agent-common
```

角色由环境变量 `AGENT_ROLE=router|order|logistics|invoice` 选择。
