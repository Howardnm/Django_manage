"""app_workflow 通知接线测试：5 个审批信号 → 对应用户收到通知。"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from app_notification.models import Notification
from app_workflow.models import WorkflowDefinition, WorkflowInstance, WorkflowTask
from app_workflow.signals import (
    workflow_started, task_created, task_completed,
    workflow_completed, task_returned,
)

# 确保类型已注册 + 信号已绑定（ready() 已导入，此处显式作保障）
import app_workflow.notifications  # noqa: F401

User = get_user_model()


def _make_user(username):
    return User.objects.create_user(username=username, email=f'{username}@test.local', password='x')


class WorkflowSignalNotificationsTests(TestCase):
    def setUp(self):
        self.initiator = _make_user('initiator')
        self.approver1 = _make_user('approver1')
        self.approver2 = _make_user('approver2')
        self.definition = WorkflowDefinition.objects.create(name='测试流程', bpmn_xml='')
        self.instance = WorkflowInstance.objects.create(
            definition=self.definition, started_by=self.initiator, status='RUNNING',
        )

    def _task(self, task_name='节点审批', assigned_to=None, status='PENDING'):
        return WorkflowTask.objects.create(
            instance=self.instance, task_name=task_name,
            assigned_to=assigned_to, spiff_task_id='T1', status=status,
        )

    def test_workflow_started_notifies_first_pending(self):
        self._task(assigned_to=self.approver1)
        workflow_started.send(sender=object(), instance=self.instance)
        n = Notification.objects.filter(type='workflow_submitted')
        self.assertEqual(n.count(), 1)
        self.assertEqual(n.first().recipient, self.approver1)

    def test_workflow_started_notifies_when_assignee_is_initiator(self):
        """回归：发起人==首个待办审批人时，'流程发起'通知仍应送达。"""
        self._task(assigned_to=self.initiator)
        workflow_started.send(sender=object(), instance=self.instance)
        n = Notification.objects.filter(type='workflow_submitted')
        self.assertEqual(n.count(), 1)
        self.assertEqual(n.first().recipient, self.initiator)

    def test_task_created_notifies_assignee(self):
        task = self._task(assigned_to=self.approver1)
        task_created.send(sender=object(), task=task)
        n = Notification.objects.filter(type='workflow_task_assigned')
        self.assertEqual(n.count(), 1)
        self.assertEqual(n.first().recipient, self.approver1)

    def test_task_created_notifies_assignee_when_assignee_is_initiator(self):
        """回归：审批人==发起人时，待办通知不应被 actor 排除规则吞掉。"""
        task = self._task(assigned_to=self.initiator)
        task_created.send(sender=object(), task=task)
        n = Notification.objects.filter(type='workflow_task_assigned')
        self.assertEqual(n.count(), 1)
        self.assertEqual(n.first().recipient, self.initiator)

    def test_task_completed_approve_running_notifies_initiator(self):
        task = self._task(assigned_to=self.approver1)
        task_completed.send(sender=object(), task=task, user=self.approver1, action='APPROVE')
        n = Notification.objects.filter(type='workflow_approved')
        self.assertEqual(n.count(), 1)
        self.assertEqual(n.first().recipient, self.initiator)

    def test_task_completed_reject_notifies_initiator(self):
        task = self._task(assigned_to=self.approver1)
        task_completed.send(sender=object(), task=task, user=self.approver1, action='REJECT')
        n = Notification.objects.filter(type='workflow_rejected')
        self.assertEqual(n.count(), 1)
        self.assertEqual(n.first().recipient, self.initiator)

    def test_workflow_completed_notifies_initiator(self):
        workflow_completed.send(sender=object(), instance=self.instance, status='COMPLETED')
        n = Notification.objects.filter(type='workflow_completed')
        self.assertEqual(n.count(), 1)
        self.assertEqual(n.first().recipient, self.initiator)
        self.assertIsNone(n.first().actor)  # 系统通知

    def test_workflow_canceled_notifies_initiator(self):
        workflow_completed.send(sender=object(), instance=self.instance, status='CANCELED')
        n = Notification.objects.filter(type='workflow_canceled')
        self.assertEqual(n.count(), 1)
        self.assertEqual(n.first().recipient, self.initiator)

    def test_workflow_completed_rejected_skipped(self):
        """REJECTED 已由 task_completed/REJECT 发出，此处不应再发。"""
        workflow_completed.send(sender=object(), instance=self.instance, status='REJECTED')
        self.assertEqual(Notification.objects.filter(type='workflow_completed').count(), 0)
        self.assertEqual(Notification.objects.filter(type='workflow_canceled').count(), 0)

    def test_task_returned_to_initiator(self):
        task = self._task(assigned_to=self.approver1)
        task_returned.send(sender=object(), task=task, user=self.approver1, target_task=None)
        n = Notification.objects.filter(type='workflow_returned_to_initiator')
        self.assertEqual(n.count(), 1)
        self.assertEqual(n.first().recipient, self.initiator)

    def test_task_returned_to_approver(self):
        task = self._task(assigned_to=self.approver1)
        target = self._task(task_name='上级审批', assigned_to=self.approver2)
        task_returned.send(sender=object(), task=task, user=self.approver1, target_task=target)
        n = Notification.objects.filter(type='workflow_returned_to_approver')
        self.assertEqual(n.count(), 1)
        self.assertEqual(n.first().recipient, self.approver2)