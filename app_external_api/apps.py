from django.apps import AppConfig


class AppExternalApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_external_api'
    verbose_name = '外部行为日志'
