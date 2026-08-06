"""app_notification 单元测试：注册原语 + notify() 服务层。

信号→通知的接线测试已下沉到各业务 app（app_workflow / app_project /
app_trial_production），本模块只测通用于各 app 的注册表与通知发送服务。
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

# 确保各业务 app 的 notifications 模块已 import（类型已注册），
# 供 test_default_types_registered 做集成断言。虽由各 app ready() 触发，
# 此处显式导入作保障。
import app_workflow.notifications  # noqa: F401
import app_project.notifications  # noqa: F401
import app_trial_production.notifications  # noqa: F401

from .models import Notification
from .registry import (
    register_ntype, get_ntype, get_registry, NotificationType,
)
from .services import notify

User = get_user_model()


def _make_user(username, **kwargs):
    """创建测试用户（自定义 User 模型要求唯一 email）。"""
    defaults = {'email': f'{username}@test.local'}
    defaults.update(kwargs)
    return User.objects.create_user(username=username, password='x', **defaults)


class RegistryTests(TestCase):
    def test_register_and_get_ntype(self):
        before = set(get_registry().keys())
        register_ntype(NotificationType(
            code='test.event', label='测试事件', verb_template='{name} 发生',
            recipients=lambda c: [],
        ))
        self.assertIn('test.event', get_registry())
        ntype = get_ntype('test.event')
        self.assertEqual(ntype.label, '测试事件')
        self.assertEqual(ntype.channel, 'inbox')
        self.assertIsNone(get_ntype('no.such.type'))
        # 清理，避免污染其他测试
        del get_registry()['test.event']
        self.assertEqual(set(get_registry().keys()), before)

    def test_duplicate_register_raises(self):
        register_ntype(NotificationType(
            code='test.dup', label='重复', verb_template='x', recipients=lambda c: [],
        ))
        with self.assertRaises(ValueError):
            register_ntype(NotificationType(
                code='test.dup', label='重复2', verb_template='y', recipients=lambda c: [],
            ))
        del get_registry()['test.dup']

    def test_default_types_registered(self):
        """各业务 app 下沉注册的类型应全部就绪（集成断言）。"""
        expected = {
            'workflow_submitted', 'workflow_task_assigned', 'workflow_approved',
            'workflow_rejected', 'workflow_returned_to_approver',
            'workflow_returned_to_initiator', 'workflow_completed',
            'workflow_canceled', 'project.node_updated',
            'production_order.state_changed',
        }
        self.assertTrue(expected.issubset(set(get_registry().keys())))


class NotifyServiceTests(TestCase):
    def setUp(self):
        self.user_a = _make_user('a')
        self.user_b = _make_user('b')

    def test_notify_creates_and_excludes_actor(self):
        # recipients 解析出 a、b；actor=a，应只剩 b 收到
        register_ntype(NotificationType(
            code='test.event', label='测试', verb_template='{name} 发生',
            recipients=lambda c: [self.user_a, self.user_b],
        ))
        notify('test.event', actor=self.user_a, name='事件A')
        n = Notification.objects.filter(type='test.event')
        self.assertEqual(n.count(), 1)
        self.assertEqual(n.first().recipient, self.user_b)
        self.assertEqual(n.first().verb, '事件A 发生')
        self.assertEqual(n.first().channel, 'inbox')
        del get_registry()['test.event']

    def test_notify_unknown_type_is_noop(self):
        notify('no.such.type', name='x')  # 不应抛异常
        self.assertEqual(Notification.objects.count(), 0)

    def test_notify_no_recipients_is_noop(self):
        register_ntype(NotificationType(
            code='test.empty', label='空', verb_template='x',
            recipients=lambda c: [],
        ))
        notify('test.empty')
        self.assertEqual(Notification.objects.count(), 0)
        del get_registry()['test.empty']