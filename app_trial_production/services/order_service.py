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
                     test_item_ids=None, mold_matrix=None,
                     packaging_desc='', storage_location='', remark=''):
        """
        创建排产工单 — 仅创建工单本身 + 配方明细。
        注塑/测试任务延迟到前序阶段完成后触发（check_and_advance）。

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

        order = ProductionOrder.objects.create(
            trial_code=trial_code,
            project_id=project_id,
            project_node_id=project_node_id,
            process_profile_id=process_profile_id,
            creator=user,
            packaging_desc=packaging_desc,
            storage_location=storage_location,
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

        # 存储待触发子任务配置（不立即创建，等前序阶段完成后触发）
        if test_item_ids:
            order.test_items.set(test_item_ids)
        if mold_matrix:
            has_any_mold = any(m.get('mold_id') for m in mold_matrix)
            if has_any_mold:
                import json
                order.pending_mold_config = json.dumps(mold_matrix)

        if total_qty > 0 or test_item_ids or mold_matrix:
            order.save()

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

        任务触发时机（遵循工序先后依赖）：
        - 挤出完成       → 触发注塑任务（如有模具配置，配色任务独立并行不阻塞）
        - 注塑完成       → 触发测试任务（如有测试项目）
        """
        if order.status == 'COMPLETED':
            return

        if order.status == 'EXTRUDING':
            # 挤出完成 + 颗粒分拨完成 → 触发下游任务
            # 配色任务独立并行，不构成屏障
            ext = getattr(order, 'extrusion_task', None)
            ext_done = ext and ext.status == 'COMPLETED'
            if not ext_done:
                return

            # 颗粒分拨是注塑/测试的前置条件
            from app_trial_production.models import SampleInventory
            pellet_split_done = SampleInventory.objects.filter(
                production_order=order, type='PELLET',
            ).exists()
            if not pellet_split_done:
                return

            if order.pending_mold_config:
                # 触发注塑任务 → 推进到注塑阶段
                ProductionOrderService._create_injection_from_pending(order)
                StateMachine.transition(order, 'INJECTION_MOLDING')
                logger.info(f"Order {order.code} advanced to INJECTION_MOLDING (injection created)")
            elif order.test_items.exists():
                # 无注塑，直接触发测试任务 → 推进到测试阶段
                ProductionOrderService._create_testing_from_pending(order)
                StateMachine.transition(order, 'TESTING')
                logger.info(f"Order {order.code} advanced to TESTING (testing created, skip injection)")
            else:
                # 无后续任务 → 直接完成
                StateMachine.transition(order, 'COMPLETED')
                logger.info(f"Order {order.code} advanced to COMPLETED (no pending tasks)")

        elif order.status == 'INJECTION_MOLDING':
            # 注塑任务完成 → 触发测试任务或完成
            injection = getattr(order, 'injection_task', None)
            if injection and injection.status == 'COMPLETED':
                if order.test_items.exists():
                    ProductionOrderService._create_testing_from_pending(order)
                    StateMachine.transition(order, 'TESTING')
                    logger.info(f"Order {order.code} advanced to TESTING (testing created)")
                else:
                    StateMachine.transition(order, 'COMPLETED')
                    logger.info(f"Order {order.code} advanced to COMPLETED (no testing needed)")

        elif order.status == 'TESTING':
            # 测试任务回写完成 → 完成工单
            testing_tasks = order.testing_tasks.all()
            all_written = testing_tasks.exists() and all(
                t.status == 'RESULTS_WRITTEN_BACK' for t in testing_tasks
            )
            if all_written:
                StateMachine.transition(order, 'COMPLETED')
                logger.info(f"Order {order.code} completed")

    # ---- 子任务触发（延迟创建，不在 create_order 时立即创建） ----

    @staticmethod
    def _create_injection_from_pending(order):
        """从 pending_mold_config 创建 InjectionTask + MoldRequirement（挤出+配色完成后调用）"""
        import json
        from app_mold_injection.models import InjectionTask, MoldRequirement
        from app_formula.models import LabFormula

        mold_matrix = json.loads(order.pending_mold_config)
        formulas = list(LabFormula.objects.filter(
            code=order.trial_code, project_id=order.project_id,
        ).order_by('version'))

        task = InjectionTask.objects.create(
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
                        injection_task=task,
                        mold_id=mold_id,
                        formula=formula,
                        specimen_quantity=int(qty),
                    )

        # 清除 pending 配置，避免重复触发
        order.pending_mold_config = ''
        order.save(update_fields=['pending_mold_config'])

        logger.info(f"InjectionTask {task.pk} created from pending mold config for order {order.code}")
        return task

    @staticmethod
    def _create_testing_from_pending(order):
        """从 order.test_items 创建 TestingTask（注塑完成后调用）"""
        from app_material_testing.models import TestingTask

        task = TestingTask.objects.create(
            production_order=order,
            status='PENDING',
        )
        task.test_items.set(order.test_items.all())

        logger.info(f"TestingTask {task.pk} created from pending test items for order {order.code}")
        return task
