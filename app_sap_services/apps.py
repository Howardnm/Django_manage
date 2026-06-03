from django.apps import AppConfig


class AppSapServicesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_sap_services'
    verbose_name = 'SAP集成服务'

    def ready(self):
        import app_sap_services.signals
