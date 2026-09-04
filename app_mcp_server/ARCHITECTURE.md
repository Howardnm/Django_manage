# app_mcp_server 架构

## 目标

把 `Django_manage` 的业务查询变成 AI Agent 可调用的 MCP 工具。协议层用官方 `mcp` 2.x 的 `MCPServer`；远程走 Streamable HTTP，本地走 Stdio。

## 目录

```text
app_mcp_server/
├── core/
│   └── server.py               # MCPServer 单例（mcp）
├── serializers/                # DRF 只读 ModelSerializer → AI 扁平 JSON
├── tools/                      # @mcp.tool() 业务工具
├── management/commands/
│   └── run_mcp_server.py       # Stdio 入口
├── apps.py                     # 扫描 tools/ + autodiscover mcp_tools
└── ARCHITECTURE.md
```

Streamable HTTP **不在** Django `urls.py`。官方 SDK 返回的是 Starlette ASGI 应用，由 [Django_manage/asgi.py](../Django_manage/asgi.py) 挂到 `/mcp`。

## 分层

### 协议层

- `mcp = MCPServer("Django_manage")`
- 工具用 `@mcp.tool()`，函数名即工具名，docstring 即 description，类型注解即参数 schema

### 传输

- **Streamable HTTP**（远程）：ASGI `POST/GET/DELETE /mcp`，`StreamableHTTPSessionManager`
- **Stdio**（本地）：`mcp.run()`，`python manage.py run_mcp_server`

旧版 `GET /mcp/sse/` + `POST /mcp/messages/` 已下线。

### 业务

- Tools：同步 `def`（SDK 丢进线程跑 ORM），`raise ToolError`，`read_only_hint=True`，返回 TypedDict
- Serializers：DRF 只读 `ModelSerializer`（`Serializer(obj).data`），输出仍是扁平字符串 / float / `YYYY-MM-DD`，不是目录 HTTP 那套嵌套 REST 形状

## 新增工具

1. 在 `tools/` 新建 `.py`
2. `from app_mcp_server.core.server import mcp, READ_ONLY`，`@mcp.tool(annotations=READ_ONLY)` + 同步 `def` + 返回类型 + docstring。查不到数据时 `raise ToolError`，不要 `return "Error: ..."`
3. 重启服务

## 接入

### 远程

- URL: `http://<host>/mcp`
- Transport: `http` / `streamable-http`
- Header: `X-MCP-API-KEY`（若配置了 `MCP_API_KEY`）

必须用 ASGI。Nginx 用 `location /mcp`（无尾斜杠也能命中），`proxy_buffering off`。

### Claude Desktop

```json
"mcpServers": {
  "django-manage": {
    "command": "python",
    "args": ["D:/path/to/manage.py", "run_mcp_server"]
  }
}
```
