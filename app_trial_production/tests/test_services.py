"""ProductionOrderService tests."""
from django.test import TestCase
from django.contrib.auth import get_user_model
from common_utils.state_machine import InvalidStateTransition, StateMachine
from app_trial_production.models import ProductionOrder, ExtrusionTask

User = get_user_model()


class StateMachineTransitionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='test')

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
