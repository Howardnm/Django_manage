# app_mcp_server 架构

## 目标

把 `Django_manage` 的业务查询变成 AI Agent 可调用的 MCP 工具。协议层用官方 `mcp` 2.x 的 `MCPServer`；远程走 Streamable HTTP，本地走 Stdio。远程查询按调用人做 L1~L5 过滤。

## 目录

```text
app_mcp_server/
├── asgi.py                     # MCPASGIApp + CORS/JWT 鉴权 + mcp_lifespan
├── auth.py                     # RS256 验签 + User 映射
├── access.py                   # tool claim + AccessMixin L1~L5
├── core/
│   └── server.py               # MCPServer 单例（mcp）
├── serializers/                # DRF 只读 ModelSerializer → AI 扁平 JSON
├── tools/                      # @mcp.tool() 业务工具
├── management/commands/
│   └── run_mcp_server.py       # Stdio 入口（无 JWT，工具拒绝查询）
├── apps.py                     # 扫描 tools/ + autodiscover mcp_tools
└── ARCHITECTURE.md
```

Streamable HTTP **不在** Django `urls.py`。官方 SDK 返回的是 Starlette ASGI 应用；`MCPASGIApp` 在本模块 [asgi.py](./asgi.py)，由 [Django_manage/asgi.py](../Django_manage/asgi.py) 在 Django setup 之后挂到 `/mcp`。

## 分层

### 协议层

- `mcp = MCPServer("Django_manage")`
- 工具用 `@mcp.tool()`，函数名即工具名，docstring 即 description，类型注解即参数 schema
- `ctx: Context` 由 SDK 按类型注入，不进 JSON schema

### 传输

- **Streamable HTTP**（远程）：`MCPASGIApp`（CORS + JWT Bearer）→ `session_manager.handle_request`；host lifespan `session_manager.run()`
- **Stdio**（本地）：`mcp.run()`，`python manage.py run_mcp_server`。无 JWT，工具 `ToolError`

旧版 `GET /mcp/sse/` + `POST /mcp/messages/` 已下线。

### 鉴权

```
Authorization: Bearer <JWT>
        │
        ▼
MCPASGIApp（OPTIONS 仍 204）
        │  PyJWT RS256：签名 / exp / iat / alg
        │  失败 → 401（对外不枚举原因；原因在 logs/mcp.log）
        ▼
resolve_user（email → username=employeeNo/sub；is_active）
        │  映射失败 → 401
        ▼
request.state.mcp_jwt + mcp_user_id
        │
        ├─ initialize / tools/list：不查 tool
        └─ tools/call：require_tool → gated_qs(AccessMixin)
```

身份只信 ASGI 验签后的 `request.state`。`ctx.headers` 是客户端输入，不能当身份。同步工具跑在 `anyio.to_thread` 里，**不要用 ContextVar**。

`tool` claim 必须等于工具函数名。握手可以用任意有效用户 JWT。

用户映射：`email`（strip + iexact）优先；缺失再用 `employeeNo` 查 `User.employee_no`；再否则 `sub` 先工号再 `username`。不创建用户，不按 JWT `departmentName` / `employeeName` 改资料。

### 业务

- Tools：同步 `def`（SDK 丢进线程跑 ORM），先 `gated_qs` 再 keyword，`raise ToolError`，`read_only_hint=True`，返回 TypedDict
- Serializers：DRF 只读 `ModelSerializer`（`Serializer(obj).data`），输出仍是扁平字符串 / float / `YYYY-MM-DD`
- 项目必须走 `ProjectAccessMixin.get_queryset()`，才能保留 `members` / `sales_members` 穿透
- `get_material_and_formulas` 两道门：材料走 Material mixin，关联配方再走 Formula mixin；配方不可见则 `associated_formulas_history=[]`

## 新增工具

1. 在 `tools/` 新建 `.py`
2. `from app_mcp_server.core.server import mcp, READ_ONLY`，`@mcp.tool(annotations=READ_ONLY)` + 同步 `def` + `ctx: Context` + 返回类型 + docstring。查询走 `gated_qs` / `gated_get`。查不到数据时 `raise ToolError("未找到或无权访问")`
3. 重启服务

## 接入

### 远程

- URL: `http://<host>/mcp`
- Transport: `http` / `streamable-http`
- Header: `Authorization: Bearer <JWT>`（IT / Sunwill 网关按工具签发）

必须用 ASGI。Nginx 用 `location /mcp`（无尾斜杠也能命中），`proxy_buffering off`。

### Claude Desktop

Stdio 通道没有 JWT，工具会拒绝查询。本地调试请配公钥 + 自签 JWT 走 HTTP，或仅用于协议握手。

```json
"mcpServers": {
  "django-manage": {
    "command": "python",
    "args": ["D:/path/to/manage.py", "run_mcp_server"]
  }
}
```
