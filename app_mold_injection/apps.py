from django.apps import AppConfig


class AppMoldInjectionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_mold_injection'
    verbose_name = '模具注塑中心'

    def ready(self):
        self._register_state_machines()

    def _register_state_machines(self):
        from common_utils.state_machine import StateMachine
        from app_mold_injection.models import InjectionTask

        StateMachine.register(InjectionTask, {
            'PENDING': ['IN_PROGRESS'],
            'IN_PROGRESS': ['COMPLETED'],
            'COMPLETED': [],
        })
