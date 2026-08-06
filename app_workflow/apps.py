from django.apps import AppConfig


class AppWorkflowConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_workflow'
    verbose_name = '工作流管理'

    def ready(self):
        import app_workflow.signals
        # 声明式接入通知：注册审批通知类型 + 绑定信号（import 即完成）
        import app_workflow.notifications
