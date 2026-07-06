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
                     test_item_ids=None,
                     sap_material_code='',
                     packaging_desc='', storage_location='', remark=''):
        """
        创建排产工单 — 仅创建工单本身 + 配方明细。
        注塑/测试任务延迟到前序阶段完成后触发（check_and_advance）。
        模具需求通过 MoldRequirement inline formset 单独保存。

        Args:
            user: 创建人
            trial_code: 实验单号
            project_id: 项目ID
            project_node_id: 项目节点ID（可选）
            process_profile_id: 工艺方案ID（可选）
            formula_details: list of dict {formula_id, planned_quantity, needs_color_matching}
            test_item_ids: list of TestConfig IDs
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
            sap_material_code=sap_material_code,
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

        # 存储待触发子任务配置
        if test_item_ids:
            order.test_items.set(test_item_ids)

        if total_qty > 0 or test_item_ids:
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
        """审批通过后接单 — 变更状态并创建下游任务。

        正常流程：ACCEPTED → 创建 ExtrusionTask(PENDING)
        竞品工单（skip_extrusion=True）：ACCEPTED → 直接创建 InjectionTask → INJECTION_MOLDING
        """
        from app_trial_production.models import ExtrusionTask

        StateMachine.transition(order, 'ACCEPTED', user)

        if order.skip_extrusion:
            # 竞品工单：跳过挤出，直接创建注塑任务
            from app_mold_injection.models import MoldRequirement
            # 确保模具需求已关联到工单
            has_mold = order.mold_requirements.filter(
                injection_task__isnull=True
            ).exists()
            if has_mold:
                ProductionOrderService._create_injection_from_pending(order)
            StateMachine.transition(order, 'INJECTION_MOLDING', user)
            logger.info(f"Order {order.code} accepted → INJECTION_MOLDING (skip_extrusion)")
        else:
            # 正常流程：创建待生产挤出任务
            ExtrusionTask.objects.get_or_create(
                production_order=order,
                defaults={'status': 'PENDING'},
            )
            logger.info(f"Order {order.code} accepted → EXTRUDING pending")

        return order

    @staticmethod
    @transaction.atomic
    def start_extrusion(order, user):
        """
        开始挤出生产 — 将已有 PENDING ExtrusionTask 推进到 IN_PROGRESS，
        并创建 ColorMatchingTask。仅在 order.status == ACCEPTED 时允许调用。
        """
        from app_trial_production.models import ExtrusionTask
        from app_color_center.models import ColorMatchingTask

        # 获取已有挤出任务（accept_order 已创建 PENDING），推进到 IN_PROGRESS
        extrusion_task, _ = ExtrusionTask.objects.get_or_create(
            production_order=order,
            defaults={'status': 'PENDING'},
        )
        if extrusion_task.status == 'PENDING':
            extrusion_task.operator = user
            StateMachine.transition(extrusion_task, 'IN_PROGRESS', user)
        elif extrusion_task.status == 'IN_PROGRESS':
            # 操作员可能不同，更新为当前操作员
            if extrusion_task.operator_id != user.pk:
                extrusion_task.operator = user
                extrusion_task.save(update_fields=['operator'])

        # 创建配色任务
        needs_color = order.formula_details.filter(
            needs_color_matching=True).exists()
        ColorMatchingTask.objects.get_or_create(
            production_order=order,
            defaults={
                'operator': None,
                'status': 'PENDING' if needs_color else 'NOT_REQUIRED',
            },
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
            if not ext.pellet_split_completed:
                return

            if order.mold_requirements.filter(injection_task__isnull=True).exists():
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
        """从 order.mold_requirements（planning阶段）创建 InjectionTask 并关联 MoldRequirement"""
        from app_mold_injection.models import InjectionTask

        plans = order.mold_requirements.filter(injection_task__isnull=True)
        if not plans.exists():
            return None

        task = InjectionTask.objects.create(
            production_order=order,
            source='ORDER',
            status='PENDING',
        )
        # 将规划阶段的 MoldRequirement 关联到新建的注塑任务
        plans.update(injection_task=task)

        # 将工单下未关联的 FOR_INJECTION 颗粒链接到该注塑任务
        from app_trial_production.models import SampleInventory
        linked = SampleInventory.objects.filter(
            production_order=order,
            type='PELLET',
            sub_type='FOR_INJECTION',
            status='IN_LAB',
            injection_task__isnull=True,
        ).update(injection_task=task)
        if linked:
            logger.info(
                f"Linked {linked} FOR_INJECTION samples to InjectionTask {task.pk}"
            )

        logger.info(
            f"InjectionTask {task.pk} created from {plans.count()} mold plans "
            f"for order {order.code}"
        )
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
