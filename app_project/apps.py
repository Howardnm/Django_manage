from django.apps import AppConfig


class AppProjectConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_project'
    verbose_name = '项目进度'

    def ready(self):
        # 【关键】导入信号
        import app_project.utils.signals
