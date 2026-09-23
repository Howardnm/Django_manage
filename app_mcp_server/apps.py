import importlib
import logging
import pkgutil

from django.apps import AppConfig, apps
from django.utils.module_loading import module_has_submodule

from . import tools as tools_pkg
from .core import registry

logger = logging.getLogger(__name__)


class AppMcpServerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_mcp_server'
    verbose_name = 'MCP Server Framework'

    def ready(self):
        """在 Django 启动时加载所有 MCP 工具，并把加载结果记进 registry。

        两条发现路径的失败都**记录而不中断启动**：工具缺一个不影响其余工具，
        而启动失败会让 agent 连工具列表都拿不到。失败由 get_mcp_health 报给 agent。
        """
        self._load_tool_modules()
        self._discover_mcp_tools()

    def _load_tool_modules(self):
        """扫描并加载 app_mcp_server/tools/ 下的所有子模块。"""
        try:
            discovered = list(pkgutil.iter_modules(tools_pkg.__path__))
        except Exception as exc:
            registry.record_module(
                "app_mcp_server.tools", False, f"{type(exc).__name__}: {exc}",
            )
            logger.error("MCP: 工具目录扫描失败: %s", exc, exc_info=True)
            return

        for _loader, module_name, _is_pkg in discovered:
            full_module_name = f"app_mcp_server.tools.{module_name}"
            try:
                importlib.import_module(full_module_name)
            except Exception as exc:
                registry.record_module(
                    full_module_name, False, f"{type(exc).__name__}: {exc}",
                )
                logger.error(
                    "MCP: 工具模块加载失败 %s: %s", module_name, exc, exc_info=True,
                )
            else:
                registry.record_module(full_module_name, True)
                logger.info("MCP: Automatically loaded tool module: %s", module_name)

    def _discover_mcp_tools(self):
        """发现各 app 下的 mcp_tools.py。

        等价于 django.utils.module_loading.autodiscover_modules('mcp_tools')，
        但有一处刻意的差异：Django 原版对「模块存在但 import 失败」会 raise
        （见其源码末行 `if module_has_submodule(...): raise`），那会让整个服务起不来。
        这里与 tools/ 扫描保持一致：记录 + 日志，交给 get_mcp_health 上报。
        """
        for app_config in apps.get_app_configs():
            if not module_has_submodule(app_config.module, "mcp_tools"):
                continue
            full_module_name = f"{app_config.name}.mcp_tools"
            try:
                importlib.import_module(full_module_name)
            except Exception as exc:
                registry.record_module(
                    full_module_name, False, f"{type(exc).__name__}: {exc}",
                )
                logger.error(
                    "MCP: mcp_tools 加载失败 %s: %s", app_config.name, exc, exc_info=True,
                )
            else:
                registry.record_module(full_module_name, True)
                logger.info("MCP: autodiscovered %s", full_module_name)
