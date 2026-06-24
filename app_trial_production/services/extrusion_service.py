import logging
from django.db import transaction
from django.utils import timezone

from common_utils.state_machine import StateMachine

logger = logging.getLogger(__name__)


class ExtrusionTaskService:
    """挤出任务业务"""

    @staticmethod
    @transaction.atomic
    def start_task(task, user):
        """开始挤出任务"""
        if not task.operator_id:
            task.operator = user
            task.save(update_fields=['operator'])
        StateMachine.transition(task, 'IN_PROGRESS', user)

        # 同步推进工单状态
        order = task.production_order
        if order.status == 'ACCEPTED':
            StateMachine.transition(order, 'EXTRUDING', user)

    @staticmethod
    @transaction.atomic
    def save_record(task, params, user):
        """
        保存挤出参数记录（不改变状态）。

        Args:
            task: ExtrusionTask 实例
            params: dict 包含所有参数字段
            user: 记录人
        """
        for field in task.ALL_PARAM_FIELDS:
            if field in params:
                setattr(task, field, params[field])

        if 'remark' in params:
            task.remark = params['remark']

        task.recorded_by = user
        task.save()

    @staticmethod
    @transaction.atomic
    def complete_task(task, user):
        """
        完成挤出任务 → 调用并行屏障检查。
        实际产量由后续颗粒分拨汇总得出，不在此处写入。
        """
        StateMachine.transition(task, 'COMPLETED', user)

        from .order_service import ProductionOrderService
        ProductionOrderService.check_and_advance(task.production_order)
