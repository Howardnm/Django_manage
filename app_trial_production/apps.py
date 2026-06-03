from django.apps import AppConfig


class AppTrialProductionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_trial_production'
    verbose_name = '试验排产'

    def ready(self):
        import app_trial_production.signals
