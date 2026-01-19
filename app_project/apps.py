from django.apps import AppConfig


class AppProjectConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_project'

    def ready(self):
        # 【关键】导入信号
        import app_project.utils.signals
