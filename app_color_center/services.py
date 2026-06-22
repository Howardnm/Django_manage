import logging
from django.db import transaction

from common_utils.state_machine import StateMachine

logger = logging.getLogger(__name__)


class ColorMatchingTaskService:
    """配色任务业务"""

    @staticmethod
    @transaction.atomic
    def start_task(task, user):
        """开始配色任务"""
        if not task.operator_id:
            task.operator = user
            task.save(update_fields=['operator'])
        StateMachine.transition(task, 'IN_PROGRESS', user)

    @staticmethod
    def mark_not_required(task):
        """标记无需配色"""
        StateMachine.transition(task, 'NOT_REQUIRED')

    @staticmethod
    @transaction.atomic
    def complete_task(task, user):
        """
        完成配色任务 → 调用并行屏障检查。
        配色数据本身已保存在 app_formula.ColorPowderBOM 中。
        如果任务仍在 PENDING 状态，自动先转为 IN_PROGRESS。
        """
        if task.status == 'PENDING':
            if not task.operator_id:
                task.operator = user
                task.save(update_fields=['operator'])
            StateMachine.transition(task, 'IN_PROGRESS', user)

        StateMachine.transition(task, 'COMPLETED', user)

        # 检查并行屏障（挤出+配色均完成 → 推进工单）
        from app_trial_production.services.order_service import ProductionOrderService
        ProductionOrderService.check_and_advance(task.production_order)
