import json
import logging

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import ValidationError

from app_mcp_server.core import registry
from app_mcp_server.responses import error_out

logger = logging.getLogger(__name__)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


class _SafeMCPServer(MCPServer):
    """兜底：逃到协议层的失败也转成结构化信封。

    `safe_tool` 只管得住工具函数体内的异常。参数类型校验失败（LLM 常把
    `project_id` 传成字符串）、工具名拼错、以及将来漏套 `safe_tool` 的新工具，
    都会在更外层炸掉并被 SDK 压成 is_error=true 的纯文本。这里统一收口，
    保证 /mcp 的 tools/call 永不返回裸报错。

    另外把注册期的静默失败记进 registry，供 get_mcp_health 报给 agent。
    """

    def add_tool(self, fn, *args, **kwargs):
        """记录重名注册。

        SDK 的行为是打一行 warning 然后**丢弃后来者**，返回值也被上层丢掉，
        所以除了在这里拦，没有别的可观测痕迹。被丢弃的工具对 agent 等于不存在。
        """
        tool_name = kwargs.get("name") or getattr(fn, "__name__", "")
        if tool_name and self._tool_manager.get_tool(tool_name) is not None:
            fn_module = getattr(fn, "__module__", "")
            registry.record_duplicate(tool_name, fn_module)
            logger.error(
                "MCP duplicate tool dropped name=%s module=%s"
                "（先注册者生效，本次注册被丢弃）",
                tool_name, fn_module,
            )
        return super().add_tool(fn, *args, **kwargs)

    def registered_tools(self) -> list:
        """同步枚举已注册工具。

        SDK 没有公开的同步访问器（`list_tools()` 是 async），把私有属性
        `_tool_manager` 的访问收在这一处，别扩散到业务代码里。
        """
        return self._tool_manager.list_tools()

    async def call_tool(self, name, arguments, context=None):
        try:
            return await super().call_tool(name, arguments, context)
        except MCPError:
            # 协议级错误（如需要客户端补充输入）照旧上抛，不改语义
            raise
        except UnexpectedToolError:
            logger.exception("MCP tool crashed tool=%s args=%s", name, arguments)
            envelope = error_out("INTERNAL")
        except ToolError as exc:
            message = self._argument_message(exc)
            logger.info("MCP bad call tool=%s args=%s reason=%s", name, arguments, message)
            envelope = error_out("INVALID_ARGUMENT", message)
        except Exception:
            logger.exception("MCP tool call failed at protocol layer tool=%s args=%s", name, arguments)
            envelope = error_out("INTERNAL")

        logger.info("MCP envelope returned tool=%s code=%s", name, envelope["error_code"])
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(envelope, ensure_ascii=False, indent=2))],
            structured_content={"result": envelope},
            is_error=False,
        )

    @staticmethod
    def _argument_message(exc):
        """参数校验失败只报字段名，不回显被拒的值（与 SDK 的日志口径一致）。"""
        if isinstance(exc.__cause__, ValidationError):
            fields = sorted({
                ".".join(str(part) for part in err["loc"])
                for err in exc.__cause__.errors()
            })
            return f"参数校验失败：{'、'.join(fields)}"
        # SDK 给 ToolError 套了 "Error executing tool X: " 前缀，别透给 agent
        message = str(exc)
        marker = "Error executing tool "
        if message.startswith(marker):
            _, sep, rest = message.partition(": ")
            message = rest if sep else ""
        return message or "调用参数不被接受：工具名可能不存在，或参数不符合 inputSchema。"


mcp = _SafeMCPServer("Django_manage")
