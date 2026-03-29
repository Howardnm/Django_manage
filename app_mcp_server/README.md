# Django MCP Server Framework (重构版)

本模块是一个高性能、模块化的 **Model Context Protocol (MCP)** 框架，旨在将 `Django_manage` 的研发数据（项目、材料、配方、BOM、物性）安全地暴露给 AI Agent（如 Dify, Claude Desktop, Cursor）。

## 🌟 核心特性

- **双协议支持**: 完美支持 **HTTP/SSE** (用于 Dify 等云端 Agent) 和 **Stdio** (用于本地 IDE/AI 客户端)。
- **零配置加载**: 智能扫描 `tools/` 目录，新增工具只需新建 `.py` 文件并使用 `@mcp_site.register` 装饰器，无需修改配置。
- **深度数据关联**: 整合了项目进度、商务档案、实验配方与成品材料的全链路查询，支持 AI 循序渐进地深入挖掘。
- **高性能异步**: 全程采用 `AnyIO` 与 Django 异步视图，支持长连接与并发工具调用。
- **统一序列化**: 自动处理 `Decimal`、日期等 JSON 序列化问题，确保 AI 返回结果的标准性。

---

## 🚀 快速启动

### 1. 安装依赖
```bash
pip install mcp[server] asgiref anyio
```

### 2. 启动方式

#### 模式 A：HTTP/SSE 模式 (推荐用于 Dify)
随 Django 主服务启动（必须使用 ASGI 容器）：
```bash
uvicorn Django_manage.asgi:application --host 0.0.0.0 --port 8000
```
- **SSE 连接端点**: `http://<your-ip>:8000/mcp/sse/`
- **消息 POST 端点**: `http://<your-ip>:8000/mcp/messages/`

#### 模式 B：Stdio 模式 (用于本地 Claude/IDE)
```bash
python manage.py run_mcp_server
```

---

## 🛠️ AI 接入配置 (以 Dify 为例)

1. 在 Dify 工具页添加 **MCP 工具**。
2. **传输类型**: 选择 `SSE`。
3. **URL**: 填写 `http://你的服务器IP:8000/mcp/sse/`。
4. **Auth (可选)**: 配置 Header `X-MCP-API-KEY` (需在 Django `settings.py` 中定义)。

---

## 🔍 可用 AI 指令示例

| 业务领域 | 示例提问 (AI 会自动匹配工具) |
| :--- | :--- |
| **项目管理** | "查找比亚迪相关的项目，并告诉我目前的详细进度和最新备注" |
| **材料库** | "搜索所有 PA66 的成品材料，显示其阻燃等级和性能指标" |
| **研发追溯** | "查看牌号 [牌号名] 的历史实验配方，包括 BOM 组成和实测物性" |
| **商务档案** | "获取项目 [项目名] 的主机厂标准文件和 2D 图纸列表" |

---

## 📂 模块化开发指南

### 如何新增一个 AI 工具？
本框架支持 **即插即用**。

1. 在 `app_mcp_server/tools/` 下新建 `my_tool.py`。
2. 编写逻辑：
   ```python
   from app_mcp_server.core.registry import mcp_site
   from app_mcp_server.serializers import serialize_xxx
   
   @mcp_site.register(
       name="get_data", 
       description="描述何时调用此工具",
       parameters={ "type": "object", "properties": { "id": {"type": "integer"} } }
   )
   async def get_data(id):
       # 你的 Django ORM 逻辑 (使用 sync_to_async)
       return {"data": "..."}
   ```
3. 重启 Django 即可生效。

---

## 🛡️ 安全与维护

- **只读设计**: 所有工具默认仅提供查询接口。
- **Session 管理**: 内置过时会话自动清理机制，防止长连接导致的内存泄漏。
- **详细架构**: 请参阅 [ARCHITECTURE.md](./ARCHITECTURE.md)。

---
*Powered by MCP Framework for Django_manage*
