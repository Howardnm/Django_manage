# app_mcp_server 架构

## 目标

把 `Django_manage` 的业务查询变成 AI Agent 可调用的 MCP 工具。协议层用官方 `mcp` 2.x 的 `MCPServer`；远程走 Streamable HTTP，本地走 Stdio。远程查询按调用人做 L1~L5 过滤。

## 目录

```text
app_mcp_server/
├── asgi.py                     # MCPASGIApp + CORS/JWT 鉴权 + mcp_lifespan
├── auth.py                     # RS256 验签 + User 映射
├── access.py                   # tool claim + AccessMixin L1~L5
├── responses.py                # 返回信封：ToolErrorOut / ToolFailure / safe_tool
├── core/
│   ├── server.py               # MCPServer 单例（mcp）+ 协议层兜底
│   └── registry.py             # 注册期可观测状态（加载失败 / 重名）
├── serializers/                # DRF 只读 ModelSerializer → AI 扁平 JSON
├── tools/
│   ├── projects.py materials.py formulas.py   # 业务工具
│   └── health.py               # get_mcp_health：注册健康 + 调用人权限自检
├── management/commands/
│   └── run_mcp_server.py       # Stdio 入口（无 JWT，工具拒绝查询）
├── apps.py                     # 扫描 tools/ + 发现各 app 的 mcp_tools
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
Authorization: Bearer <token>
        │
        ├─ mcp_ 前缀 → 个人 API Key（哈希、开通开关、未过期）
        └─ 否则     → PyJWT RS256（签名 / exp / iat / alg）
        │  失败 → 401（对外不枚举原因；原因在 logs/mcp.log）
        ▼
JWT：resolve_user（email → employee_no → username）
API Key：已绑定 User
        │  映射失败 / 未开通 / 过期 → 401
        ▼
request.state.mcp_jwt + mcp_user_id
        │
        ├─ initialize / tools/list：不查 tool
        └─ tools/call：JWT 校验 tool claim；API Key 跳过 claim
           → gated_qs(AccessMixin) 仍走 L1~L5
              INFO 记 user / tool / args / claims
```

身份只信 ASGI 验签后的 `request.state`。`ctx.headers` 是客户端输入，不能当身份。同步工具跑在 `anyio.to_thread` 里，**不要用 ContextVar**。

`tool` claim 必须等于工具函数名。握手可以用任意有效用户 JWT。

用户映射：`email`（strip + iexact）优先；缺失再用 `employeeNo` 查 `User.employee_no`；再否则 `sub` 先工号再 `username`。不创建用户，不按 JWT `departmentName` / `employeeName` 改资料。

### 业务

- Tools：同步 `def`（SDK 丢进线程跑 ORM），先 `gated_qs` 再 keyword，`read_only_hint=True`
- Serializers：DRF 只读 `ModelSerializer`（`Serializer(obj).data`），输出扁平字符串 / float / `YYYY-MM-DD`
- **空属性一律输出 `null`**，不用 `"N/A"` / `"Unknown"` / `""` 之类的字符串哨兵——agent 必须能区分
  "没有值"和"值就是 N/A"。字段不会因为没值而消失（见下 `business_info`）。`base.py` 的
  `blank_to_none` 就是干这个的
- 项目必须走 `ProjectAccessMixin.get_queryset()`，才能保留 `members` / `sales_members` 穿透
- `get_material_and_formulas` 两道门：材料走 Material mixin，关联配方再走 Formula mixin。
  配方不可见时保留材料数据，另给 `associated_formulas_total` / `associated_formulas_hidden`
  计数 + `associated_formulas_note` 说明。注意 **L4/L5 隔离是静默过滤、不抛异常**，所以"被挡住"
  只能靠与未隔离 queryset 的计数比对发现，`except` 抓不到
- 需要区分"没值"和"没读到"时用 `WarningMixin`：`files` / `associated_files` 读取失败给 `null` +
  `warnings`，而不是塌成 `[]`
- `app_repository` 有 `post_save(Project)` 信号「立项即开档案」，所以每个新项目都自带一个
  `ProjectRepository`；`business_info is None` 只出现在档案被删/历史数据上

### 返回值与失败（agent 永远拿到结构化数据）

失败**不**用逃逸异常表达：SDK 会把逃到协议层的异常压成
`CallToolResult(content=[TextContent("Error executing tool X: ...")], is_error=True)`
—— 没有 `structuredContent`，非 `ToolError` 的异常连原因都丢。

| 场景 | 形状 |
| :--- | :--- |
| 单对象工具成功 | 对象本身（可能带 `warnings`） |
| 搜索类工具成功 | `{ok: true, data: [...], total, returned, has_more}`，零命中/被截断时另给 `hint` |
| 任何工具失败 | `{ok: false, error_code, message, hint}` |

> 因为返回注解写成 `SuccessOut \| ToolErrorOut`，SDK 会包一层，
> 线上 `structuredContent` 实际是 `{"result": <上面任一种>}`，`is_error` 恒为 `false`。

- **结果上限**：搜索工具都有 `limit: int | None = None`。**不传 = 不限**（行为与加 limit 之前一致，
  不做额外 COUNT，`total == returned`、`has_more=False`）；传了才 `qs[:limit]` + `qs.count()`，
  并给出真实 `total` / `has_more` / 截断提示。`limit < 1` → `INVALID_ARGUMENT`
- 错误码与文案集中在 `responses.py`：`NO_IDENTITY` / `ACCOUNT_UNAVAILABLE` / `TOOL_NOT_ALLOWED` /
  `NO_MODULE_ACCESS`（调用人层面，准入在**任何查询之前**拦下）/ `NO_PERMISSION` vs `NOT_FOUND`
  （记录层面区分，hint 里明确劝阻换编号试探）/ `INVALID_ARGUMENT` / `INTERNAL`
- 工具内抛 `ToolFailure(code)`，由 `safe_tool` 转信封；未预期异常 → `INTERNAL`（原因进服务端日志）
- 每个工具的 docstring **必须**写明失败信封与 `error_code` 的读法——description 是每个客户端都会
  展示的部分，`test_every_tool_description_documents_the_envelope` 守着这条
- `_SafeMCPServer.call_tool` 是协议层兜底：参数类型校验失败（LLM 常把 id 传成字符串）、
  工具名拼错、漏套 `safe_tool` 的新工具，同样返回 `INVALID_ARGUMENT` / `INTERNAL` 信封

### 注册期可观测性

注册阶段的失败是静默的，agent 只会看到"工具不存在"。三处都被挡在 `core/registry.py` 里：

| 失败 | 原行为 | 现在 |
| :--- | :--- | :--- |
| `tools/*.py` import 失败 | `logger.error`，工具缺失 | 记进 `LOAD_REPORT` |
| 其它 app 的 `mcp_tools.py` import 失败 | **Django 启动崩**（`autodiscover_modules` 会 raise） | 记进 `LOAD_REPORT`，服务照常起 |
| 工具重名 | SDK 打 warning 后**丢弃后来者** | `_SafeMCPServer.add_tool` 记进 `DUPLICATES` |
| 返回注解读不出 schema | 只 `logger.info`，工具注册但无 structured output | `get_mcp_health` 报为 `unguarded` |

上表第 2、3、4 行是 `get_mcp_health` 要解决的：agent 调 `tools/list` 看不到被丢弃的工具，
也没有别的渠道知道为什么。**注意**第 2 行是刻意偏离 Django 默认行为的（原版会让服务起不来），
理由与 `tools/` 扫描保持一致：缺一个工具不该拖垮整个服务，而失败会被上报。

`get_mcp_health` 同时做**调用人权限自检**：每个业务模块能否准入、卡在 L1/L2/L3 哪一层。
只报调用人自己的权限，不泄露业务记录；模块表从工具模块导入 mixin 与权限码，避免漂移。

## 新增工具

1. 在 `tools/` 新建 `.py`
2. 两个装饰器 + 联合返回注解 + docstring（docstring 即 description，要写明失败信封的读法）：

```python
from mcp.server.mcpserver.context import Context
from app_mcp_server.access import gated_get, gated_qs
from app_mcp_server.core.server import mcp, READ_ONLY
from app_mcp_server.responses import ToolErrorOut, ToolFailure, safe_tool, search_ok, validate_limit

@mcp.tool(annotations=READ_ONLY)
@safe_tool                                            # 必须在 mcp.tool 下面
def get_data(ctx: Context, id: int) -> ModelOut | ToolErrorOut:
    """描述何时调用此工具。

    On failure returns {"ok": false, "error_code": ..., "message": ..., "hint": ...} instead of raising.
    """
    obj = gated_get(ctx, "get_data", Model.objects.all(), SomeAccessMixin, "app.view_model", pk=id)
    return serialize_model(obj)

@mcp.tool(annotations=READ_ONLY)
@safe_tool
def search_data(ctx: Context, keyword: str = "", limit: int | None = None) -> SearchOut | ToolErrorOut:
    """描述何时调用此工具。Omit limit to get all matches."""
    limit = validate_limit(limit)
    qs = gated_qs(ctx, "search_data", Model.objects.all(), SomeAccessMixin, "app.view_model")
    total = qs.count() if limit is not None else None
    if limit is not None:
        qs = qs[:limit]
    data = [serialize_model(o) for o in qs]
    return search_ok(
        data,
        empty_hint="放宽 keyword 后重试。",
        total=total,
        has_more=total > len(data) if total is not None else False,
    )
```

3. 重启服务

`gated_get` / `raise_empty` 已负责区分「无权」与「不存在」，工具里不要自己写
`raise ToolError("未找到或无权访问")`。

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
