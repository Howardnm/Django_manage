import json
import asyncio
import logging
from typing import List, Dict, Any, Optional
from mcp.server import Server, NotificationOptions
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from django.core.serializers.json import DjangoJSONEncoder
from .registry import mcp_site

logger = logging.getLogger(__name__)

# 初始化单例 MCP Server
mcp_server = Server("Django_manage_HTTP_MCP")

def mcp_json_dumps(obj):
    """MCP 专用 JSON 序列化逻辑，处理 Decimal 等特殊类型"""
    return json.dumps(obj, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)

@mcp_server.list_tools()
async def list_tools() -> List[Tool]:
    """列出所有已注册的工具"""
    tools_data = mcp_site.get_tools_metadata()
    logger.info(f"MCP: list_tools called, returning {len(tools_data)} tools.")
    return [
        Tool(
            name=t["name"],
            description=t["description"],
            inputSchema=t["inputSchema"]
        ) for t in tools_data
    ]

@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict):
    """工具调用适配器"""
    logger.info(f"MCP: call_tool -> {name} | Args: {arguments}")
    try:
        result = await mcp_site.call_tool(name, arguments)
        
        # 检查是否已经是 MCP 标准返回内容
        is_mcp_standard = False
        if isinstance(result, list) and len(result) > 0:
            first = result[0]
            if isinstance(first, (TextContent, ImageContent, EmbeddedResource)):
                is_mcp_standard = True
            elif isinstance(first, dict) and "type" in first and first["type"] in ["text", "image", "resource"]:
                is_mcp_standard = True
        
        if is_mcp_standard:
            return result
            
        # 否则统一序列化为 JSON 文本
        text_content = mcp_json_dumps(result) if isinstance(result, (dict, list)) else str(result)
        return [TextContent(type="text", text=text_content)]
        
    except Exception as e:
        logger.error(f"MCP Tool Error [{name}]: {str(e)}", exc_info=True)
        return [TextContent(type="text", text=f"Error: {str(e)}")]
