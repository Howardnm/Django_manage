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

Stdio（`run_mcp_server`）没有 JWT：工具会报「此通道未启用身份认证」，**不会**返回全表。

```http
Authorization: Bearer <JWT>
```

缺少或错误的 token 返回 `401`，并带 `WWW-Authenticate: Bearer`。

## 新增工具

在 `app_mcp_server/tools/` 新建 `.py`：

```python
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from app_mcp_server.access import gated_qs
from app_mcp_server.core.server import mcp, READ_ONLY

@mcp.tool(annotations=READ_ONLY)
def get_data(ctx: Context, id: int) -> dict:
    """描述何时调用此工具。"""
    qs = gated_qs(ctx, "get_data", Model.objects.all(), SomeAccessMixin, "app.view_model")
    obj = qs.filter(pk=id).first()
    if not obj:
        raise ToolError("未找到或无权访问")
    return ...
```

重启 Django 后自动注册。其它 app 可提供 `mcp_tools.py`，同样 `from app_mcp_server.core.server import mcp`。

## 可用指令示例

| 业务领域 | 示例提问 |
| :--- | :--- |
| **项目管理** | 查找比亚迪相关的项目，并告诉我目前的详细进度和最新备注 |
| **材料库** | 搜索所有 PA66 的成品材料，显示其阻燃等级和性能指标 |
| **研发追溯** | 查看牌号 [牌号名] 的历史实验配方，包括 BOM 组成和实测物性 |
| **商务档案** | 获取项目 [项目名] 的主机厂标准文件和 2D 图纸列表 |

详细架构见 [ARCHITECTURE.md](./ARCHITECTURE.md)。
