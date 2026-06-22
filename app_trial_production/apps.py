from django.apps import AppConfig


class AppTrialProductionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_trial_production'
    verbose_name = '试验排产'

    def ready(self):
        import app_trial_production.signals  # noqa: F401

        # 注册关联对象路由器 — 审批流程中可跳转回工单详情
        from django.urls import reverse
        from app_workflow.utils import related_object_router
        from app_trial_production.models import ProductionOrder

        related_object_router.register(
            ProductionOrder,
            url_resolver=lambda obj: reverse('trial_order_detail', kwargs={'pk': obj.pk}),
            display_name_resolver=lambda obj: obj.code,
            person_resolver=lambda obj: obj.creator,
        )

        # 注册状态机转换规则
        self._register_state_machines()

    def _register_state_machines(self):
        from common_utils.state_machine import StateMachine
        from app_trial_production.models import (
            ProductionOrder, ExtrusionTask,
        )

        # ProductionOrder: 8 状态 → 7 条转换规则
        StateMachine.register(ProductionOrder, {
            'DRAFT': ['WORKFLOW_RUNNING', 'CANCELED'],
            'WORKFLOW_RUNNING': ['ACCEPTED', 'DRAFT', 'CANCELED'],
            'ACCEPTED': ['EXTRUDING'],
            'EXTRUDING': ['INJECTION_MOLDING', 'COMPLETED'],
            'INJECTION_MOLDING': ['TESTING'],
            'TESTING': ['COMPLETED'],
            'COMPLETED': [],
            'CANCELED': [],
        })

        # ExtrusionTask: 3 状态 → 2 条规则
        StateMachine.register(ExtrusionTask, {
            'PENDING': ['IN_PROGRESS'],
            'IN_PROGRESS': ['COMPLETED'],
            'COMPLETED': [],
        })

        # InjectionTask 状态机已迁移至 app_mold_injection.apps
