from django.apps import AppConfig


class AppColorCenterConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_color_center'
    verbose_name = '配色中心'

    def ready(self):
        self._register_state_machines()

    def _register_state_machines(self):
        from common_utils.state_machine import StateMachine
        from app_color_center.models import ColorMatchingTask

        StateMachine.register(ColorMatchingTask, {
            'PENDING': ['IN_PROGRESS', 'NOT_REQUIRED'],
            'IN_PROGRESS': ['COMPLETED'],
            'COMPLETED': [],
            'NOT_REQUIRED': [],
        })
