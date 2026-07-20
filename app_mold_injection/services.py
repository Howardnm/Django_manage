import logging
from django.db import transaction

from common_utils.state_machine import StateMachine

logger = logging.getLogger(__name__)


class InjectionTaskService:
    """注塑任务业务"""

    @staticmethod
    def parse_specimen_outputs(task, post_data):
        """从矩阵 POST 数据解析样条产出记录。

        遍历 task.mold_requirements 及其 formula_details，
        提取每个 (模具, 配方版本) 单元格的产出/合格数量，
        结合每行的存放位置和批次标签。

        Args:
            task: InjectionTask 实例
            post_data: request.POST (QueryDict)

        Returns:
            list of dict [{mold_id, specimen_count, specimen_qualified,
                           storage_location, batch_label, formula_id}]
        """
        specimen_outputs = []
        for req in task.mold_requirements.all().select_related('mold').prefetch_related('formula_details'):
            location = post_data.get(f'location_{req.mold_id}', '').strip()
            batch = post_data.get(f'batch_{req.mold_id}', '').strip()
            for detail in req.formula_details.all():
                fid = str(detail.formula_id) if detail.formula_id else 'none'
                try:
                    qty = int(post_data.get(f'qty_{req.mold_id}_{fid}', '0'))
                except (ValueError, TypeError):
                    qty = 0
                if qty <= 0:
                    continue
                try:
                    qualified = int(post_data.get(f'qualified_{req.mold_id}_{fid}', '0'))
                except (ValueError, TypeError):
                    qualified = 0
                specimen_outputs.append({
                    'mold_id': req.mold_id,
                    'specimen_count': qty,
                    'specimen_qualified': qualified,
                    'storage_location': location,
                    'batch_label': batch,
                    'formula_id': detail.formula_id,
                })
        return specimen_outputs

    @staticmethod
    @transaction.atomic
    def start_task(task, user):
        """开始注塑任务"""
        if not task.operator_id:
            task.operator = user
            task.save(update_fields=['operator'])
        StateMachine.transition(task, 'IN_PROGRESS', user)

    @staticmethod
    @transaction.atomic
    def complete_task(task, user, specimen_outputs=None):
        """
        完成注塑任务 — 样条入库 + 关联测试任务。

        Args:
            task: InjectionTask 实例
            user: 操作员
            specimen_outputs: list of dict {
                mold_id, specimen_count, specimen_qualified,
                storage_location, batch_label
            }
        """
        StateMachine.transition(task, 'COMPLETED', user)

        # 样条入库
        if specimen_outputs:
            from app_trial_production.services.sample_service import SampleInventoryService
            SampleInventoryService.create_specimen_batch(task, specimen_outputs)

        # 将关联的 FOR_INJECTION 颗粒标记为已消耗
        from app_trial_production.models import SampleInventory
        from django.utils import timezone as tz
        consumed = SampleInventory.objects.filter(
            injection_task=task,
            type='PELLET',
            sub_type='FOR_INJECTION',
            status='IN_LAB',
        ).update(status='CONSUMED', updated_at=tz.now())
        if consumed:
            logger.info(
                f"Marked {consumed} FOR_INJECTION samples as CONSUMED "
                f"for InjectionTask {task.pk}"
            )

        # 渠道A：推进排产工单状态
        production_order = task.production_order
        if production_order:
            from app_trial_production.services.order_service import ProductionOrderService
            ProductionOrderService.check_and_advance(production_order)

        return task
