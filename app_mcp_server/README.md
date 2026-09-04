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
        "X-MCP-API-KEY": "<optional>"
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

`settings.MCP_API_KEY` 来自环境变量 `MCP_API_KEY`。未设置或为空则跳过鉴权。

客户端请求头：`X-MCP-API-KEY: <key>`

## 新增工具

在 `app_mcp_server/tools/` 新建 `.py`：

```python
from mcp.server.mcpserver.exceptions import ToolError
from app_mcp_server.core.server import mcp, READ_ONLY

@mcp.tool(annotations=READ_ONLY)
def get_data(id: int) -> dict:
    """描述何时调用此工具。"""
    obj = ...
    if not obj:
        raise ToolError(f"Not found: {id}")
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
