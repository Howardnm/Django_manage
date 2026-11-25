from django.db import transaction

from common_utils.state_machine import StateMachine


class InjectionTaskService:
    """注塑任务业务"""

    @staticmethod
    @transaction.atomic
    def complete_task(task, user):
        """完成注塑任务：操作员取本次完成的用户，再做状态迁移；有排产工单时推进工单。"""
        task.operator = user
        task.save(update_fields=['operator'])
        StateMachine.transition(task, 'COMPLETED', user)

        production_order = task.production_order
        if production_order:
            from app_trial_production.services.order_service import ProductionOrderService
            ProductionOrderService.check_and_advance(production_order)

        return task
