import asyncio
import sys
import logging
from django.core.management.base import BaseCommand
from mcp.server.stdio import stdio_server
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions
from ...core.server import mcp_server

# 在 Stdio 模式下，禁用向 stdout 打印任何业务日志，因为 stdout 被 MCP 协议占用
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Run MCP (Model Context Protocol) Server in Stdio mode for local AI tools (e.g. Claude Desktop)'

    def handle(self, *args, **options):
        """
        Management Command entry: start the async loop for Stdio mode.
        """
        # 强制配置日志，将所有日志重定向到 stderr，防止干扰 stdout 协议流
        handler = logging.StreamHandler(sys.stderr)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("Starting Django MCP Server (Stdio Mode)...")
        try:
            asyncio.run(self.main())
        except KeyboardInterrupt:
            logger.info("MCP Server stopped by user.")

    async def main(self):
        """
        Execute the global mcp_server instance via Stdio transport.
        Uses the same core tools registered in app_mcp_server.tools.
        """
        async with stdio_server() as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="Django_manage_MCP_Stdio",
                    server_version="1.0.0",
                    capabilities=mcp_server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
