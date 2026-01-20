from django.apps import AppConfig

class AppRawMaterialConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_raw_material'
    verbose_name = '原材料库'

    def ready(self):
        import app_raw_material.signals
