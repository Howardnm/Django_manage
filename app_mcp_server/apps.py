import importlib
import logging
import pkgutil
from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules
from . import tools as tools_pkg

logger = logging.getLogger("app_mcp_server.apps")

class AppMcpServerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_mcp_server'
    verbose_name = 'MCP Server Framework'

    def ready(self):
        """
        在 Django 启动时，智能且自动地加载所有 MCP 工具。
        """
        # 1. 智能扫描并加载本项目 app_mcp_server.tools 包下的所有子模块
        # 这确保了 tools/ 文件夹下新增的任何 .py 文件都会被自动加载
        try:
            for loader, module_name, is_pkg in pkgutil.iter_modules(tools_pkg.__path__):
                full_module_name = f"app_mcp_server.tools.{module_name}"
                try:
                    importlib.import_module(full_module_name)
                    logger.info(f"MCP: Automatically loaded tool module: {module_name}")
                except Exception as e:
                    logger.error(f"MCP: Error loading tool module {module_name}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"MCP: Critical error during dynamic tool discovery: {e}")

        # 2. 自动发现并加载其他已安装 App 下的 mcp_tools.py 
        # 遵循 Django 标准插件发现机制
        autodiscover_modules('mcp_tools')
        logger.info("MCP: Global autodiscover for 'mcp_tools' completed.")
