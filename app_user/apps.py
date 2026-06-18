"""app_user 的 Django AppConfig。

导出: AppUserConfig。
"""

from django.apps import AppConfig


class AppUserConfig(AppConfig):
    """app_user 应用配置。在 ready() 中加载信号。"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_user'
    verbose_name = '权限管控中心'

    def ready(self):
        """应用启动时导入信号模块以连接信号处理器。"""
        import app_user.signals
