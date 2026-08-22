from django.apps import AppConfig


class AppMaterialTestingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_material_testing'
    verbose_name = '材料测试中心'

    def ready(self):
        self._register_state_machines()
        self._register_attachments()

    def _register_state_machines(self):
        from common_utils.state_machine import StateMachine
        from app_material_testing.models import TestingTask

        StateMachine.register(TestingTask, {
            'PENDING': ['IN_PROGRESS'],
            'IN_PROGRESS': ['COMPLETED'],
            'COMPLETED': ['IN_PROGRESS', 'RESULTS_WRITTEN_BACK'],
            'RESULTS_WRITTEN_BACK': [],
        })

    def _register_attachments(self):
        from app_attachment.registry import register_attachment
        from app_attachment.configs import AttachmentConfig
        from app_material_testing.models import TestingTask
        from app_material_testing.mixins import TestingAccessMixin

        register_attachment(AttachmentConfig(
            parent_model=TestingTask,
            access_mixin=TestingAccessMixin,
            view_permission='app_material_testing.view_testingtask',
            add_permission='app_material_testing.change_testingtask',
            delete_permission='app_material_testing.change_testingtask',
            categories=[
                ('REPORT', '测试报告'),
                ('OTHER', '其他文件'),
            ],
            folder_id_resolver=lambda t: str(t.pk),
        ))
