from django.apps import AppConfig


class AppDifySyncConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_dify_sync'
    verbose_name = 'Dify 数据同步'

    def ready(self):
        # 导入信号处理器，确保 Django 启动时加载它们
        import app_dify_sync.signals
