# app_mcp_server 架构设计与接入指南 (重构版)

## 1. 核心目标
本模块是一个高度模块化、零配置自动加载的 **MCP (Model Context Protocol) 框架层**。它将 `Django_manage` 的复杂业务逻辑转化为 AI Agent (如 Dify, Claude Desktop) 可调用的标准工具，支持 **HTTP/SSE** 和 **Stdio** 双模式传输。

---

## 2. 目录结构 (Tree)

```text
app_mcp_server/
├── core/                       # 【核心基础设施】
│   ├── registry.py             # 工具注册中心 (@mcp_site.register)
│   ├── server.py               # MCP Server 单例及 JSON-RPC 适配
│   └── sessions.py             # AnyIO 异步会话与生命周期管理
├── transports/                 # 【传输适配层】
│   ├── sse.py                  # SSE (Server-Sent Events) 事件流生成器
│   └── http.py                 # HTTP POST 消息解包与路由逻辑
├── serializers/                # 【序列化层】数据对象转 AI 友好格式
│   ├── base.py                 # 基础格式化工具 (日期等)
│   ├── material.py             # 成品材料序列化
│   ├── formula.py              # 实验配方序列化 (BOM/物性)
│   └── project.py              # 项目档案与进度序列化
├── tools/                      # 【业务工具库】
│   ├── materials.py            # 材料查询工具
│   ├── formulas.py             # 配方查询工具
│   └── projects.py             # 项目全景查询工具
├── management/                 # 【命令行接口】
│   └── commands/
│       └── run_mcp_server.py   # Stdio 模式入口 (本地调试/Claude Desktop)
├── views.py                    # 【接入端点】Django HTTP 视图
├── urls.py                     # 路由配置 (/sse/, /messages/)
├── apps.py                     # 自动发现逻辑 (pkgutil 动态加载 tools)
└── ARCHITECTURE.md             # 本架构说明文档
```

---

## 3. 分层逻辑详解

### 3.1 核心层 (Core Layer)
- **`mcp_site` (Registry)**: 业务逻辑与协议层的防火墙。业务代码只需关注 Django ORM，通过装饰器描述工具，无需引用 MCP SDK。
- **`mcp_server` (Server)**: 统一处理协议握手、工具列表上报、异常捕获以及 Decimal 等特殊类型的 JSON 序列化。
- **`SessionManager`**: 解决 HTTP 无状态协议与 MCP 长连接之间的矛盾。支持 Session 活动追踪和过时自动清理。

### 3.2 传输层 (Transport Layer)
- **SSE (Remote)**: 专为 Dify 等云端 AI Agent 设计。保持长连接，下发 `endpoint` 和 `message` 事件。
- **Stdio (Local)**: 专为 Claude Desktop, Cursor 设计。通过 `python manage.py run_mcp_server` 直接运行，协议走标准输入输出。

### 3.3 业务适配层 (Business Adapter)
- **Tools**: 纯异步实现 (`async def`)，通过 `sync_to_async` 安全调用 Django ORM。
- **Serializers**: 负责将复杂的数据库关联关系（如 `Project` -> `Repository` -> `BOM`）扁平化，提供“循序渐进”的数据深度。

---

## 4. 开发者指南：如何新增一个 AI 工具？

本模块支持 **“全自动扫描注册”**，无需修改 `apps.py` 或 `views.py`。

1. **创建文件**: 在 `tools/` 目录下新建一个 Python 文件（如 `custom_tool.py`）。
2. **编写逻辑**:
   ```python
   from app_mcp_server.core.registry import mcp_site
   from app_mcp_server.serializers import serialize_xxx
   
   @mcp_site.register(
       name="my_new_tool",
       description="向 AI 描述这个工具的作用",
       parameters={ "type": "object", "properties": { ... } }
   )
   async def my_new_tool(param1):
       # 你的业务逻辑
       return result
   ```
3. **重启服务**: 重启后，AI Agent 将自动感知并拉取到新工具。

---

## 5. 接入配置

### 5.1 Dify (云端接入)
- **URL**: `http://<your-ip>:<port>/mcp/sse/`
- **Transport**: `SSE`
- **Auth**: Header `X-MCP-API-KEY` (根据 settings.py 配置)

### 5.2 Claude Desktop (本地接入)
在 `claude_desktop_config.json` 中添加：
```json
"mcpServers": {
  "django-manage": {
    "command": "python",
    "args": ["D:/path/to/manage.py", "run_mcp_server"]
  }
}
```

---
*Created and maintained by MCP Framework for Django_manage*
