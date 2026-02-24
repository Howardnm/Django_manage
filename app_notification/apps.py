from django.apps import AppConfig


class AppNotificationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_notification'
    verbose_name = '通知中心'

    def ready(self):
        # 导入信号处理器，确保 Django 启动时加载它们
        import app_notification.signals
