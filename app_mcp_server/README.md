# Django MCP Server

本模块将 `Django_manage` 的研发数据（项目、材料、配方、BOM、物性）通过 **Model Context Protocol** 暴露给 AI Agent（Claude Code、Cursor、Dify 等）。

远程传输为官方 **Streamable HTTP**（`mcp==2.1.1` 的 `MCPServer`），挂在 ASGI 的 `/mcp`。本地调试走 Stdio。

## 核心特性

- **Streamable HTTP**：单端点 `GET/POST/DELETE /mcp`，兼容现代 MCP 客户端。
- **Stdio**：`python manage.py run_mcp_server`，给 Claude Desktop / 本地 IDE。
- **零配置加载**：扫描 `tools/`，新增工具只需 `@mcp.tool()` + docstring。
- **只读**：工具默认只查，不写。

## 启动

必须用 **ASGI**（uvicorn 或 gunicorn + `UvicornWorker`），不要用 `runserver`/WSGI。

```bash
uvicorn Django_manage.asgi:application --host 127.0.0.1 --port 8000
```

- **远程端点**: `http://<host>:8000/mcp`
- **传输类型**: `http` / `streamable-http`（不要再选 SSE）

Stdio：

```bash
python manage.py run_mcp_server
```

## 客户端配置

### Claude Code / Cursor

```json
{
  "mcpServers": {
    "django-manage": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp",
      "headers": {
        "Authorization": "Bearer <JWT 或个人 mcp_ API Key>"
      }
    }
  }
}
```

### Claude Desktop（本地）

```json
{
  "mcpServers": {
    "django-manage": {
      "command": "python",
      "args": ["D:/path/to/manage.py", "run_mcp_server"]
    }
  }
}
```

### Dify

传输选 **Streamable HTTP**（不要 SSE），URL 填 `http://<host>/mcp`。

## 鉴权

远程 `/mcp` 接受两种 Bearer：

1. **IT RS256 JWT**（网关按工具签发）
2. **个人 MCP API Key**（`mcp_` 前缀，管理员在 User 后台勾选开通后，用户在个人中心生成，90 天过期）

无公钥、坏签名、未知用户、过期或未开通的个人 Key 一律 `401`，不区分原因。具体原因写在服务端 `logs/mcp.log`（本地可设 `DEBUG=True` 或 `DJANGO_LOG_LEVEL=DEBUG`）。验签成功后会把 JWT claims JSON 打进日志；个人 Key 只记用户与前缀，不记录明文。工具调用还会记 `args=`（`tools/call` 的 arguments JSON），方便对照谁用什么参数查了什么。不记录原始 JWT / Authorization / API Key 明文。

JWT claims：

| claim | 作用 |
| :--- | :--- |
| `sub` / `employeeNo` / `email` | 映射本系统 User：email 优先，否则 `employeeNo` → `User.employee_no`；再否则 `sub` → 工号，再回退 `username` |
| `tool` | **仅** `tools/call` 校验，必须等于工具函数名（如 `search_projects`） |
| `exp` / `iat` | 必填；`MCP_JWT_LEEWAY` 默认 30 秒 |

握手（`initialize` / `tools/list`）只验身份，不查 `tool`。Sunwill 网关每次 HTTP 都应带新 JWT。个人 API Key 调用 `tools/call` **不校验** `tool` claim，可调全部只读工具，仍走该用户的 L1~L5。

查询结果走与 Web 端相同的 L1~L5（含项目协同成员 / 销售成员穿透）。JWT 里的 `departmentName` **不**用于隔离。

Stdio（`run_mcp_server`）没有 JWT：工具会返回 `NO_IDENTITY`（此通道未启用身份认证），**不会**返回全表。

```http
Authorization: Bearer <JWT>
```

缺少或错误的 token 返回 `401`，并带 `WWW-Authenticate: Bearer`。

## 返回值约定

工具失败**不**靠异常表达——异常会被 SDK 压成 `isError: true` 的纯文本，agent 读不到结构。
所有工具改为返回结构化信封，`isError` 恒为 `false`，agent 用 `ok` 判别：

| 场景 | structuredContent |
| :--- | :--- |
| 单对象工具成功 | `{"result": {对象}}`，可能带 `warnings` |
| 搜索类工具成功 | `{"result": {"ok": true, "data": [...], "total": N, "returned": N, "has_more": bool}}` |
| 任何工具失败 | `{"result": {"ok": false, "error_code": ..., "message": ..., "hint": ...}}` |

`hint` 是给 agent 的操作建议（例如「该记录存在但不在你的可见范围内，请不要用其他编号反复试探」）。
错误码：`NO_IDENTITY`、`ACCOUNT_UNAVAILABLE`、`TOOL_NOT_ALLOWED`、`NO_MODULE_ACCESS`、
`NO_PERMISSION`、`NOT_FOUND`、`INVALID_ARGUMENT`、`INTERNAL`。

「不存在」与「无权」**分开返回**：无权时直接告知是权限问题，避免调用人靠试编号探测记录是否存在。
模块级准入（角色 / 等级 / 权限码）仍在任何查询之前拦下，所以没有模块权限的人探测不到任何记录。

几条约定：

- **结果上限**：搜索工具都有 `limit` 参数，**不传就是不限**（取全部匹配）。传了会额外算真实
  `total` 并给 `has_more`，被截断时 hint 会指引缩小范围
- **空属性一律是 `null`**，不是 `"N/A"` / `"Unknown"` / `""`。字段不会因为没值而消失
  （例如项目没有业务档案时 `business_info` 是 `null`，而不是被删掉）
- **部分数据读不到时给 `null` + `warnings`**，而不是塌成 `[]`——`files: []` 才表示"确实没有附件"。
  `warnings` 还用于：项目名称匹配到多个（列出其他候选）、配方存在被隔离的更高版本
  （你拿到的是可见范围内最新版，不代表系统里没有更新的）、附件/物性摘要出现局部降级
- **数据隔离对两类工具的表现不同**：记录级 `get_*` 对不可见记录返回 `NO_PERMISSION`；
  搜索类工具的 `total` 只统计可见记录，被隔离的既不计数也不报错。所以"total=2"不等于
  "系统里只有 2 条"

## 出问题时先调 get_mcp_health

`get_mcp_health` 是只读的自检工具，agent 在以下情况应该先调它：

- 其它工具失败或返回 `error_code` 看不懂时
- 工具列表里缺了预期存在的工具
- 准备告诉用户"你看不到这些数据"之前

它报出：工具模块加载失败清单、被丢弃的重名工具、未受保护（漏套 `@safe_tool` 或无 output schema）
的工具、以及**当前调用人**在每个业务模块的准入结果与卡住的层级（L1 角色 / L2 等级 / L3 权限码）。
只报调用人自己的权限，不泄露任何业务记录。

## 新增工具

在 `app_mcp_server/tools/` 新建 `.py`：

```python
from mcp.server.mcpserver.context import Context
from app_mcp_server.access import gated_get, gated_qs
from app_mcp_server.core.server import mcp, READ_ONLY
from app_mcp_server.responses import ToolErrorOut, ToolFailure, safe_tool, search_ok

@mcp.tool(annotations=READ_ONLY)
@safe_tool                                            # 必须在 mcp.tool 下面
def get_data(ctx: Context, id: int) -> ModelOut | ToolErrorOut:
    """描述何时调用此工具，并写明失败信封怎么读。

    On failure returns {"ok": false, "error_code": ..., "message": ..., "hint": ...} instead of raising.
    """
    obj = gated_get(ctx, "get_data", Model.objects.all(), SomeAccessMixin, "app.view_model", pk=id)
    return serialize_model(obj)

@mcp.tool(annotations=READ_ONLY)
@safe_tool
def search_data(
    ctx: Context, keyword: str = "", limit: int | None = None,
) -> SearchOut | ToolErrorOut:
    """描述何时调用此工具。Omit limit to get all matches."""
    limit = validate_limit(limit)
    qs = gated_qs(ctx, "search_data", Model.objects.all(), SomeAccessMixin, "app.view_model")
    total = qs.count() if limit is not None else None
    if limit is not None:
        qs = qs[:limit]
    data = [serialize_model(o) for o in qs]
    return search_ok(
        data, empty_hint="放宽 keyword 后重试。",
        total=total, has_more=total > len(data) if total is not None else False,
    )
```

参数不合法时 `raise ToolFailure("INVALID_ARGUMENT", "……")`。查不到 / 无权不用自己判断，
`gated_get` 会区分并抛出对应错误码。serializer 里空值用 `base.blank_to_none`，不要造字符串哨兵；
部分数据读不到时用 `WarningMixin.add_warning`。

重启 Django 后自动注册。其它 app 可提供 `mcp_tools.py`，同样 `from app_mcp_server.core.server import mcp`。
**注意**：`mcp_tools.py` 加载失败以前会让 Django 起不来，现在改为记录进 `get_mcp_health`（缺一个工具
不该拖垮整个服务）。

## 可用指令示例

| 业务领域 | 示例提问 |
| :--- | :--- |
| **项目管理** | 查找比亚迪相关的项目，并告诉我目前的详细进度和最新备注 |
| **材料库** | 搜索所有 PA66 的成品材料，显示其阻燃等级和性能指标 |
| **研发追溯** | 查看牌号 [牌号名] 的历史实验配方，包括 BOM 组成和实测物性 |
| **商务档案** | 获取项目 [项目名] 的主机厂标准文件和 2D 图纸列表 |

详细架构见 [ARCHITECTURE.md](./ARCHITECTURE.md)。
