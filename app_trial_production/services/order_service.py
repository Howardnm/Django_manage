import logging
from django.db import transaction
from django.utils import timezone

from common_utils.state_machine import StateMachine

logger = logging.getLogger(__name__)


class ProductionOrderService:
    """生产工单业务编排"""

    @staticmethod
    @transaction.atomic
    def create_order(user, trial_code, project_id, project_node_id=None,
                     process_profile_id=None, formula_details=None,
                     test_item_ids=None, mold_matrix=None, remark=''):
        """
        创建排产工单 + 自动创建测试任务。

        Args:
            user: 创建人
            trial_code: 实验单号
            project_id: 项目ID
            project_node_id: 项目节点ID（可选）
            process_profile_id: 工艺方案ID（可选）
            formula_details: list of dict {formula_id, planned_quantity, needs_color_matching}
            test_item_ids: list of TestConfig IDs
            mold_matrix: list of dict {mold_id, formula_quantities: {formula_id: qty}}
            remark: 备注

        Returns:
            ProductionOrder 实例
        """
        from app_trial_production.models import (
            ProductionOrder, ProductionOrderFormulaDetail,
        )
        from app_material_testing.models import TestingTask

        order = ProductionOrder.objects.create(
            trial_code=trial_code,
            project_id=project_id,
            project_node_id=project_node_id,
            process_profile_id=process_profile_id,
            creator=user,
            remark=remark,
        )

        # 创建配方明细
        total_qty = 0
        if formula_details:
            for fd in formula_details:
                ProductionOrderFormulaDetail.objects.create(
                    production_order=order,
                    formula_id=fd['formula_id'],
                    planned_quantity=fd.get('planned_quantity', 0),
                    needs_color_matching=fd.get('needs_color_matching', False),
                )
                total_qty += float(fd.get('planned_quantity', 0))

        if total_qty > 0:
            order.quantity_planned = total_qty
            order.save(update_fields=['quantity_planned'])

        # 自动创建测试任务
        if test_item_ids:
            testing_task = TestingTask.objects.create(
                production_order=order,
                status='PENDING',
            )
            testing_task.test_items.set(test_item_ids)

        # 处理模具×配方矩阵
        if mold_matrix:
            from app_mold_injection.models import InjectionTask, MoldRequirement
            from app_formula.models import LabFormula

            formulas = list(LabFormula.objects.filter(
                code=trial_code, project_id=project_id,
            ).order_by('version'))

            has_any_mold = any(m.get('mold_id') for m in mold_matrix)
            if has_any_mold:
                injection_task = InjectionTask.objects.create(
                    production_order=order,
                    source='ORDER',
                    status='PENDING',
                )
                for mold_entry in mold_matrix:
                    mold_id = mold_entry.get('mold_id')
                    if not mold_id:
                        continue
                    quantities = mold_entry.get('formula_quantities', {})
                    for formula in formulas:
                        qty = quantities.get(str(formula.pk), 0) or quantities.get(formula.pk, 0)
                        if qty and int(qty) > 0:
                            MoldRequirement.objects.create(
                                injection_task=injection_task,
                                mold_id=mold_id,
                                formula=formula,
                                specimen_quantity=int(qty),
                            )

        logger.info(f"ProductionOrder {order.code} created by {user}")
        return order

    @staticmethod
    @transaction.atomic
    def start_workflow(order, definition, user):
        """为工单启动 BPMN 审批流程"""
        from app_workflow.services import WorkflowService

        if order.workflow_instance:
            logger.warning(f"Order {order.code} already has a workflow instance")
            return None

        has_color_matching = order.formula_details.filter(
            needs_color_matching=True).exists()
        context_data = {
            'needs_color_matching': has_color_matching,
            'order_code': order.code,
        }

        callback_config = {
            'handler': 'app_trial_production.workflow_handlers.handle_production_order_callback',
            'args': {'order_pk': order.pk},
        }

        instance = WorkflowService.start(
            definition=definition,
            started_by=user,
            related_object=order,
            context_data=context_data,
            callback_config=callback_config,
        )

        order.workflow_instance = instance
        StateMachine.transition(order, 'WORKFLOW_RUNNING', user)
        return instance

    @staticmethod
    @transaction.atomic
    def accept_order(order, user=None):
        """审批通过后接单 — 仅变更状态，不创建子任务。任务在操作员开始生产时创建。"""
        StateMachine.transition(order, 'ACCEPTED', user)
        logger.info(f"Order {order.code} accepted")
        return order

    @staticmethod
    @transaction.atomic
    def start_extrusion(order, user):
        """
        开始挤出生产 — 创建 ExtrusionTask + ColorMatchingTask，推进工单状态。
        仅在 order.status == ACCEPTED 时允许调用。
        """
        from app_trial_production.models import ExtrusionTask
        from app_color_center.models import ColorMatchingTask

        # 创建挤出任务（直接进入 IN_PROGRESS）
        extrusion_task = ExtrusionTask.objects.create(
            production_order=order,
            operator=user,
            status='IN_PROGRESS',
        )

        # 创建配色任务
        needs_color = order.formula_details.filter(
            needs_color_matching=True).exists()
        ColorMatchingTask.objects.create(
            production_order=order,
            operator=None,
            status='PENDING' if needs_color else 'NOT_REQUIRED',
        )

        # 推进工单状态: ACCEPTED → EXTRUDING
        StateMachine.transition(order, 'EXTRUDING', user)

        logger.info(f"Order {order.code} extrusion started by {user}")
        return extrusion_task

    @staticmethod
    def schedule_extrusion(order, scheduled_dt, scheduled_end=None):
        """设置/更新工单的挤出排产时间（scheduled_dt=None 表示取消排期）"""
        order.extrusion_scheduled_date = scheduled_dt
        order.extrusion_scheduled_end = scheduled_end
        order.save(update_fields=[
            'extrusion_scheduled_date', 'extrusion_scheduled_end', 'updated_at',
        ])

    @staticmethod
    def check_and_advance(order):
        """
        检查子任务完成情况，自动推进工单状态。
        在 ExtrusionTask / ColorMatchingTask / InjectionTask / TestingTask 完成时调用。
        """
        if order.status == 'COMPLETED':
            return

        if order.status == 'EXTRUDING':
            # 挤出+配色并行屏障
            ext = getattr(order, 'extrusion_task', None)
            color = getattr(order, 'color_task', None)
            ext_done = ext and ext.status == 'COMPLETED'
            color_done = (
                color is None
                or color.status in ('COMPLETED', 'NOT_REQUIRED')
            )
            if ext_done and color_done:
                # 无注塑任务 → 跳过注塑和测试，直接完成
                injection = getattr(order, 'injection_task', None)
                if injection is None:
                    StateMachine.transition(order, 'COMPLETED')
                    logger.info(f"Order {order.code} advanced to COMPLETED (skip injection)")
                else:
                    StateMachine.transition(order, 'INJECTION_MOLDING')
                    logger.info(f"Order {order.code} advanced to INJECTION_MOLDING")

        elif order.status == 'INJECTION_MOLDING':
            # 注塑任务完成 → 推进到测试
            injection = getattr(order, 'injection_task', None)
            if injection and injection.status == 'COMPLETED':
                StateMachine.transition(order, 'TESTING')
                logger.info(f"Order {order.code} advanced to TESTING")

        elif order.status == 'TESTING':
            # 测试任务回写完成 → 完成工单
            testing_tasks = order.testing_tasks.all()
            all_written = testing_tasks.exists() and all(
                t.status == 'RESULTS_WRITTEN_BACK' for t in testing_tasks
            )
            if all_written:
                StateMachine.transition(order, 'COMPLETED')
                logger.info(f"Order {order.code} completed")
