from django.apps import AppConfig


class AppWorkflowConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_workflow'
    verbose_name = '工作流管理'

    def ready(self):
        import app_workflow.signals
