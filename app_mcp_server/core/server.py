from mcp.server import MCPServer
from mcp.types import ToolAnnotations

mcp = MCPServer("Django_manage")
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
