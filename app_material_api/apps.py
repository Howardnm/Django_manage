from django.apps import AppConfig

class AppMaterialApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_material_api'
    verbose_name = '材料库集成服务'

    def ready(self):
        # 核心：在此处导入信号，确保集成逻辑在系统启动时激活
        import app_material_api.integration.signals
