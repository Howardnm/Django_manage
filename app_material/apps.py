from django.apps import AppConfig


class AppMaterialConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_material' # 确保这里的路径和你 settings.py 里的一致
    verbose_name = '材料库'