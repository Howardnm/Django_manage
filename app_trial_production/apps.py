from django.apps import AppConfig


class AppTrialProductionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_trial_production'
    verbose_name = '试验排产'

    def ready(self):
        import app_trial_production.signals

        # 注册附件配置
        from app_attachment.registry import register_attachment
        from app_attachment.configs import AttachmentConfig
        from app_trial_production.models.testing import TestingOrder
        from app_trial_production.mixins import TestingTaskAccessMixin

        register_attachment(AttachmentConfig(
            parent_model=TestingOrder,
            access_mixin=TestingTaskAccessMixin,
            view_permission='app_trial_production.view_testingorder',
            add_permission='app_trial_production.change_testingorder',
            delete_permission='app_trial_production.change_testingorder',
            categories=[
                ('REPORT', '测试报告'),
                ('OTHER', '其他文件'),
            ],
            folder_id_resolver=lambda t: str(t.pk),
        ))
