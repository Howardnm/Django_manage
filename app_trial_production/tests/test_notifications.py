"""app_trial_production 通知接线测试：排产工单状态流转 → 项目相关成员收到通知。"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from app_notification.models import Notification
from app_project.models import Project
from app_trial_production.models import ProductionOrder
from common_utils.state_machine import StateMachine

# 确保类型已注册 + state_changed 已绑定（ready() 已导入，此处显式作保障）
import app_trial_production.notifications  # noqa: F401

User = get_user_model()


def _make_user(username):
    return User.objects.create_user(username=username, email=f'{username}@test.local', password='x')


class ProductionOrderNotificationsTests(TestCase):
    def test_order_state_change_notifies_project_stakeholders(self):
        manager = _make_user('manager')
        member = _make_user('member')
        sales = _make_user('sales')
        outsider = _make_user('outsider')
        operator = _make_user('operator')
        project = Project.objects.create(name='项目A', manager=manager)
        project.members.create(user=member)
        project.sales_members.create(user=sales)
        order = ProductionOrder.objects.create(creator=operator, project=project)

        # 触发状态流转（DRAFT → WORKFLOW_RUNNING）
        # state_changed 信号现走 transaction.on_commit，需显式捕获回调。
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            StateMachine.transition(order, 'WORKFLOW_RUNNING', operator)
        self.assertEqual(len(callbacks), 1)

        qs = Notification.objects.filter(type='production_order.state_changed')
        # 每个接收者一条通知（负责人 + 协同成员 + 销售成员 = 3）
        self.assertEqual(qs.count(), 3)
        recipients = set(qs.values_list('recipient_id', flat=True))
        # 负责人 + 协同成员 + 销售成员，排除无关用户与操作者本人（exclude_actor 默认 True）
        self.assertEqual(recipients, {manager.pk, member.pk, sales.pk})
        self.assertNotIn(outsider.pk, recipients)
        self.assertNotIn(operator.pk, recipients)

        n = qs.first()
        self.assertIn(order.code, n.verb)
        self.assertIn('流程中', n.verb)  # WORKFLOW_RUNNING 的中文标签
        self.assertEqual(n.channel, 'inbox')

    def test_order_state_change_skipped_without_project(self):
        creator = _make_user('creator')
        order = ProductionOrder.objects.create(creator=creator)  # 无 project
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            StateMachine.transition(order, 'WORKFLOW_RUNNING', creator)
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(
            Notification.objects.filter(type='production_order.state_changed').count(), 0)