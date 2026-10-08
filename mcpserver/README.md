# order-agent MCP Server

独立进程，通过 MCP Streamable HTTP 暴露订单/售后/退款/物流/发票业务工具。
**假数据唯一归属本目录**（`data/fake_data.py`），业务逻辑在 `service/`。

## 启动

```bash
cd mcpserver
python main.py
# 默认 http://127.0.0.1:8010/mcp
```

环境变量：`MCP_HOST`、`MCP_PORT`、`MCP_PATH`。

专家进程启动时会 `list_tools` 发现并装配业务工具；REST / 证据查询经 backend `app.service` 适配器调用本服务。须先于专家与依赖假数据的 REST 启动。

## Tools

| 领域 | 工具名 |
|------|--------|
| 订单 | `query_orders`, `get_order_detail`, `get_order_by_no` |
| 售后 | `list_after_sales`, `get_after_sale_detail`, `get_after_sale_progress` |
| 退款 | `list_refunds`, `get_refund_detail`, `get_refund_progress`, `create_refund` |
| 物流 | `get_logistics_by_order_no`, `get_logistics_tracking` |
| 发票 | `get_invoice`, `list_invoices_by_order`, `create_invoice_download_urls` |
