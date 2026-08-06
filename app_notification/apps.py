from django.apps import AppConfig


class AppNotificationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_notification'
    verbose_name = '通知中心'

    def ready(self):
        # 本模块为纯通用核心，不注册任何业务通知类型。
        # 各业务 app 在自己的 AppConfig.ready() 中导入其 notifications.py
        # 来定义类型 + 声明式绑定信号（见 app_workflow / app_project / app_trial_production）。
        pass