import logging
from django.db import transaction

from common_utils.state_machine import StateMachine

logger = logging.getLogger(__name__)


class InjectionTaskService:
    """注塑任务业务"""

    @staticmethod
    @transaction.atomic
    def create_from_order(production_order, operator_id=None,
                          injection_params_note='', mold_requirements=None):
        """
        渠道A：从排产工单创建注塑任务。

        Args:
            production_order: ProductionOrder 实例
            operator_id: 注塑操作员ID (User pk or None)
            injection_params_note: 注塑工艺备注
            mold_requirements: list of dict {mold_id, formula_id, specimen_quantity}
        """
        from django.contrib.auth import get_user_model
        from app_mold_injection.models import InjectionTask, MoldRequirement, MoldRequirementFormulaDetail

        User = get_user_model()
        operator = User.objects.get(pk=operator_id) if operator_id else None

        task = InjectionTask.objects.create(
            production_order=production_order,
            source='ORDER',
            operator=operator,
            injection_params_note=injection_params_note,
            status='PENDING',
        )

        if mold_requirements:
            for req in mold_requirements:
                if req.get('specimen_quantity', 0) > 0:
                    mr = MoldRequirement.objects.create(
                        injection_task=task,
                        mold_id=req['mold_id'],
                    )
                    MoldRequirementFormulaDetail.objects.create(
                        mold_requirement=mr,
                        formula_id=req.get('formula_id'),
                        specimen_quantity=req['specimen_quantity'],
                    )

        logger.info(f"InjectionTask created from order {production_order.code}")
        return task

    @staticmethod
    @transaction.atomic
    def create_from_inventory(sample_inventory, project=None, operator_id=None,
                              injection_params_note='', mold_requirements=None):
        """
        渠道B：从样品库取料创建独立注塑任务。

        Args:
            sample_inventory: SampleInventory 实例（待打样颗粒）
            project: 关联项目（用于后期关联测试结果）
            operator_id: 注塑操作员ID (User pk or None)
            injection_params_note: 注塑工艺备注
            mold_requirements: list of dict {mold_id, formula_id, specimen_quantity}
        """
        from django.contrib.auth import get_user_model
        from app_mold_injection.models import InjectionTask, MoldRequirement, MoldRequirementFormulaDetail

        User = get_user_model()
        operator = User.objects.get(pk=operator_id) if operator_id else None

        task = InjectionTask.objects.create(
            source='INVENTORY',
            sample_inventory=sample_inventory,
            source_project=project,
            operator=operator,
            injection_params_note=injection_params_note,
            status='PENDING',
        )

        # 标记样品为已消耗
        sample_inventory.status = 'CONSUMED'
        sample_inventory.save(update_fields=['status', 'updated_at'])

        if mold_requirements:
            for req in mold_requirements:
                if req.get('specimen_quantity', 0) > 0:
                    mr = MoldRequirement.objects.create(
                        injection_task=task,
                        mold_id=req['mold_id'],
                    )
                    MoldRequirementFormulaDetail.objects.create(
                        mold_requirement=mr,
                        formula_id=req.get('formula_id'),
                        specimen_quantity=req['specimen_quantity'],
                    )

        logger.info(f"InjectionTask created from inventory {sample_inventory}")
        return task

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

        # 渠道A：推进排产工单状态
        production_order = task.production_order
        if production_order:
            from app_trial_production.services.order_service import ProductionOrderService
            ProductionOrderService.check_and_advance(production_order)

        return task
