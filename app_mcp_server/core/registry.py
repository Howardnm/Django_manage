import json
import logging
from typing import Callable, Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ToolMetadata:
    name: str
    description: str
    parameters: Dict[str, Any]

class MCPRegistry:
    """MCP 工具注册中心 - 支持插件式注册"""
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._metadata: Dict[str, ToolMetadata] = {}

    def register(self, name: str, description: str, parameters: Optional[Dict[str, Any]] = None):
        """
        装饰器：注册一个工具函数。
        :param name: AI 调用时的唯一 ID
        :param description: 给 AI 的指令，告知何时调用此工具
        :param parameters: 参数的 JSON Schema 定义
        """
        def wrapper(func: Callable):
            self._tools[name] = func
            schema = parameters or {
                "type": "object",
                "properties": {},
                "required": []
            }
            self._metadata[name] = ToolMetadata(
                name=name,
                description=description,
                parameters=schema
            )
            return func
        return wrapper

    def get_tools_metadata(self) -> List[Dict[str, Any]]:
        """获取符合 MCP 协议要求的工具元数据列表"""
        return [
            {
                "name": meta.name,
                "description": meta.description,
                "inputSchema": meta.parameters
            }
            for meta in self._metadata.values()
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """执行被注册的工具函数"""
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not found.")
        
        logger.info(f"Executing MCP Tool: {name} with arguments: {json.dumps(arguments, ensure_ascii=False)}")
        return await self._tools[name](**arguments)

# 导出全局单例
mcp_site = MCPRegistry()
