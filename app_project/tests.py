"""app_project 通知接线测试：ProjectNode 更新 → 项目负责人与成员收到通知。"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from app_notification.models import Notification
from app_project.models import Project, ProjectNode

# 确保类型已注册 + post_save 已绑定（ready() 已导入，此处显式作保障）
import app_project.notifications  # noqa: F401

User = get_user_model()


def _make_user(username):
    return User.objects.create_user(username=username, email=f'{username}@test.local', password='x')


class ProjectNodeNotificationsTests(TestCase):
    def test_node_update_notifies_manager_and_members(self):
        manager = _make_user('manager')
        member = _make_user('member')
        outsider = _make_user('outsider')
        project = Project.objects.create(name='项目A', manager=manager)
        project.members.create(user=member)
        node = ProjectNode.objects.create(project=project, stage='INIT')

        # 首次创建不通知
        self.assertEqual(Notification.objects.filter(type='project.node_updated').count(), 0)

        # 更新节点触发通知（manager + member，排除 outsider）
        node.remark = '更新备注'
        node.save()
        recipients = set(Notification.objects.filter(
            type='project.node_updated').values_list('recipient_id', flat=True))
        self.assertEqual(recipients, {manager.pk, member.pk})
        self.assertNotIn(outsider.pk, recipients)