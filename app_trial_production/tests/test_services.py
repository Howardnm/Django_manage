"""ProductionOrderService tests."""
from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model
from common_utils.state_machine import InvalidStateTransition, StateMachine
from app_formula.models import LabFormula
from app_material.models import MaterialType
from app_trial_production.models import ExtrusionTask, ProductionOrder, ProductionOrderFormulaDetail
from app_trial_production.services import ExtrusionTaskService, ProductionOrderService

User = get_user_model()


class StateMachineTransitionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='testuser@trial.dev', password='test')

    def test_valid_transition(self):
        """合法状态转换"""
        order = ProductionOrder.objects.create(creator=self.user)
        StateMachine.transition(order, ProductionOrder.Status.WORKFLOW_RUNNING, self.user)
        self.assertEqual(order.status, ProductionOrder.Status.WORKFLOW_RUNNING)

    def test_invalid_transition_raises(self):
        """非法状态转换抛出异常"""
        order = ProductionOrder.objects.create(creator=self.user)
        order.status = ProductionOrder.Status.DRAFT
        with self.assertRaises(InvalidStateTransition):
            StateMachine.transition(order, ProductionOrder.Status.COMPLETED)

    def test_timestamp_set_on_complete(self):
        """COMPLETED 转换时设置 completed_at"""
        order = ProductionOrder.objects.create(creator=self.user)
        order.extrusion_scheduled_date = None
        StateMachine.transition(order, ProductionOrder.Status.WORKFLOW_RUNNING, self.user)

        # 手动推进到完成来测试时间戳
        order.status = ProductionOrder.Status.TESTING
        order.save()
        # 注册 EXTRUDING → COMPLETED 简化为直接转换以便测试
        from common_utils.state_machine import StateMachine as SM
        transitions = SM._TRANSITIONS_MAP.get('ProductionOrder', {})
        transitions[ProductionOrder.Status.EXTRUDING] = [
            ProductionOrder.Status.INJECTION_MOLDING,
            ProductionOrder.Status.COMPLETED,
        ]
        transitions[ProductionOrder.Status.TESTING] = [
            ProductionOrder.Status.COMPLETED,
        ]
        self.assertIsNone(order.completed_at)
        StateMachine.transition(order, ProductionOrder.Status.COMPLETED)
        order.refresh_from_db()
        self.assertIsNotNone(order.completed_at)


class RecordActualQuantityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='yield_writer', email='yield@trial.dev', password='test')
        self.mt = MaterialType.objects.create(name='PA66-YIELD')
        self.v1 = LabFormula.objects.create(
            code='T-YIELD', name='配方v1', material_type=self.mt,
            creator=self.user, version=1)
        self.v2 = LabFormula.objects.create(
            code='T-YIELD', name='配方v2', material_type=self.mt,
            creator=self.user, version=2)
        self.order = ProductionOrder.objects.create(
            code='TP-YIELD', trial_code='T-YIELD', creator=self.user)

    def test_sums_finished_and_specimen_across_versions(self):
        """多版本成品颗粒与样条颗粒之和写入实际产量。"""
        ProductionOrderFormulaDetail.objects.create(
            production_order=self.order, formula=self.v1,
            finished_pellet_kg=Decimal('10.50'), specimen_pellet_kg=Decimal('1.25'))
        ProductionOrderFormulaDetail.objects.create(
            production_order=self.order, formula=self.v2,
            finished_pellet_kg=Decimal('3.00'), specimen_pellet_kg=Decimal('0.25'))

        ProductionOrderService.record_actual_quantity(self.order)

        self.order.refresh_from_db()
        self.assertEqual(self.order.quantity_actual, Decimal('15.00'))

    def test_all_zero_writes_zero_not_null(self):
        """明细都是 0 时实际产量写成 0，而不是留空。"""
        ProductionOrderFormulaDetail.objects.create(
            production_order=self.order, formula=self.v1)
        ProductionOrderFormulaDetail.objects.create(
            production_order=self.order, formula=self.v2)

        ProductionOrderService.record_actual_quantity(self.order)

        self.order.refresh_from_db()
        self.assertEqual(self.order.quantity_actual, Decimal('0'))


class ExtrusionOperatorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='extruder', email='extruder@trial.dev', password='test')
        self.order = ProductionOrder.objects.create(
            code='TP-OP', trial_code='T-OP', creator=self.user,
            status=ProductionOrder.Status.ACCEPTED)
        self.task = ExtrusionTask.objects.create(
            production_order=self.order, status=ExtrusionTask.Status.PENDING)

    def test_start_task_does_not_assign_operator(self):
        ExtrusionTaskService.start_task(self.task, self.user)

        self.task.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.task.status, ExtrusionTask.Status.IN_PROGRESS)
        self.assertIsNone(self.task.operator_id)
        self.assertIsNone(self.order.extruder_operator_id)

    def test_start_extrusion_does_not_assign_operator(self):
        ProductionOrderService.start_extrusion(self.order, self.user)

        self.task.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.task.status, ExtrusionTask.Status.IN_PROGRESS)
        self.assertIsNone(self.task.operator_id)
        self.assertIsNone(self.order.extruder_operator_id)

    def test_complete_assigns_task_and_order_operator(self):
        self.task.status = ExtrusionTask.Status.IN_PROGRESS
        self.task.save(update_fields=['status'])
        self.order.status = ProductionOrder.Status.EXTRUDING
        self.order.save(update_fields=['status'])

        ExtrusionTaskService.complete_task(self.task, self.user)

        self.task.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.task.operator_id, self.user.pk)
        self.assertEqual(self.order.extruder_operator_id, self.user.pk)
