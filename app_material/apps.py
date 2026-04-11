from django.apps import AppConfig


class AppMaterialConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_material'
    verbose_name = '材料库'

    def ready(self):
        # 核心修改：从集成层导入信号
        import app_material.integration.signals
