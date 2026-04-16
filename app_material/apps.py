from django.apps import AppConfig

class AppMaterialConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_material'
    verbose_name = '材料库'

    def ready(self):
        # 信号监听逻辑已经迁移到 app_material_api 模块
        # app_material 现在只保留模型定义和基础业务逻辑
        pass
