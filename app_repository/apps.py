from django.apps import AppConfig


class AppRepositoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_repository' # 确保这里的路径和你 settings.py 里的一致
    verbose_name = '项目档案、材料库'

    def ready(self):
        # 导入信号，使其生效
        import app_repository.utils.signals