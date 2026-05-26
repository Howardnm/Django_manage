from django.apps import AppConfig


class AppUserConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_user'
    verbose_name = '权限管控中心'

    def ready(self):
        import app_user.signals
