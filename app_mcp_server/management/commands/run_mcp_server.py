import logging
import sys

from django.core.management.base import BaseCommand

from app_mcp_server.core.server import mcp

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run MCP (Model Context Protocol) Server in Stdio mode for local AI tools (e.g. Claude Desktop)'

    def handle(self, *args, **options):
        handler = logging.StreamHandler(sys.stderr)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("Starting Django MCP Server (Stdio Mode)...")
        logger.warning(
            "Stdio 通道没有 JWT，工具会拒绝查询（此通道未启用身份认证），不会返回全表。"
        )
        try:
            mcp.run()
        except KeyboardInterrupt:
            logger.info("MCP Server stopped by user.")
