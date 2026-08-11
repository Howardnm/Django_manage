"""app_notification 单元测试：注册原语 + notify() 服务层。

信号→通知的接线测试已下沉到各业务 app（app_workflow / app_project /
app_trial_production），本模块只测通用于各 app 的注册表与通知发送服务。
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import RequestFactory
from django.template.loader import render_to_string
from django.urls import reverse

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
from .context_processors import notifications as notifications_context

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


def _make_superuser(username, **kwargs):
    """创建超级用户，绕过 RBAC 准入，聚焦"点击即已读"流程本身。"""
    defaults = {'email': f'{username}@test.local'}
    defaults.update(kwargs)
    return User.objects.create_superuser(username=username, password='x', **defaults)


class ClickToReadRegressionTests(TestCase):
    """回归测试：页头/列表点击通知 → 标记已读 → 跳转落地页。

    覆盖变更链路（header_notifictions.html / list.html 链接 → MarkAsReadView）：
    1. 点击未读通知：unread 置 False 且 302 跳转落地页。
    2. 无落地页时回退 panel_home。
    3. 模板渲染的链接确实指向 mark-as-read 端点（而非直接跳 url）。
    4. recipient 隔离：他人通知不可被标记。
    5. 重复点击已读通知不报错（幂等）。
    6. 角标计数随点击递减（context processor 集成）。
    7. "全部标记已读"等既有流程不受影响。
    """

    def setUp(self):
        self.recipient = _make_superuser('recipient')
        self.other = _make_superuser('other')
        self.client.force_login(self.recipient)

    def _make_notif(self, recipient, *, url='', verb='新增', title='标题', unread=True):
        return Notification.objects.create(
            recipient=recipient, actor=self.recipient, verb=verb,
            title=title, url=url, unread=unread, type='generic',
        )

    def test_mark_as_read_marks_and_redirects_to_landing_url(self):
        notif = self._make_notif(self.recipient, url='/project/1/detail/')
        resp = self.client.get(reverse('notification_mark_as_read', args=[notif.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/project/1/detail/')
        notif.refresh_from_db()
        self.assertFalse(notif.unread, "点击后通知应被标记为已读")

    def test_mark_as_read_without_url_falls_back_to_home(self):
        notif = self._make_notif(self.recipient, url='')
        resp = self.client.get(reverse('notification_mark_as_read', args=[notif.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('panel_home'))
        notif.refresh_from_db()
        self.assertFalse(notif.unread)

    def test_header_template_links_point_to_mark_as_read(self):
        """页头下拉：渲染出的链接必须命中 mark-as-read 端点。"""
        notif = self._make_notif(self.recipient, url='/target/')
        html = render_to_string(
            'includes/header_modules/header_notifictions.html',
            {'unread_notifications': [notif], 'unread_notification_count': 1},
        )
        endpoint = reverse('notification_mark_as_read', args=[notif.pk])
        self.assertIn(f'href="{endpoint}"', html)
        self.assertNotIn(f'href="/target/"', html)

    def test_list_page_links_point_to_mark_as_read(self):
        notif = self._make_notif(self.recipient, url='/target/')
        html = render_to_string(
            'apps/app_notification/list.html',
            {'notifications': [notif], 'is_paginated': False},
        )
        endpoint = reverse('notification_mark_as_read', args=[notif.pk])
        self.assertIn(f'href="{endpoint}"', html)
        self.assertNotIn(f'href="/target/"', html)

    def test_recipient_isolation_other_users_notification_unaffected(self):
        other_notif = self._make_notif(self.other, url='/secret/')
        resp = self.client.get(reverse('notification_mark_as_read', args=[other_notif.pk]))
        self.assertEqual(resp.status_code, 404, "他人通知应 404，不可被标记")
        other_notif.refresh_from_db()
        self.assertTrue(other_notif.unread, "他人未读状态不应被改变")

    def test_click_is_idempotent_on_already_read_notification(self):
        notif = self._make_notif(self.recipient, url='/target/', unread=False)
        resp = self.client.get(reverse('notification_mark_as_read', args=[notif.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/target/')
        notif.refresh_from_db()
        self.assertFalse(notif.unread)

    def test_unread_count_decrements_after_click(self):
        """end-to-end：点击一条后，页头角标计数应减少 1。"""
        n1 = self._make_notif(self.recipient, url='/p1/')
        n2 = self._make_notif(self.recipient, url='/p2/')
        request = RequestFactory().get('/')
        request.user = self.recipient
        ctx = notifications_context(request)
        self.assertEqual(ctx['unread_notification_count'], 2)

        # 模拟点击 n1
        self.client.get(reverse('notification_mark_as_read', args=[n1.pk]))
        ctx = notifications_context(request)
        self.assertEqual(ctx['unread_notification_count'], 1)
        self.assertEqual([n.pk for n in ctx['unread_notifications']], [n2.pk])

        # 全部已读后角标归零
        self.client.get(reverse('notification_mark_all_as_read'))
        self.assertEqual(notifications_context(request)['unread_notification_count'], 0)

    def test_mark_all_as_read_still_works(self):
        for _ in range(3):
            self._make_notif(self.recipient, url='/x/')
        mark_all_url = reverse('notification_mark_all_as_read')
        resp = self.client.get(mark_all_url, HTTP_REFERER='/notifications/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/notifications/')
        self.assertEqual(Notification.objects.filter(recipient=self.recipient, unread=True).count(), 0)

    def test_url_names_resolve(self):
        """URLConf 完整性：三个命名 URL 均应正确解析。"""
        self.assertEqual(
            reverse('notification_mark_as_read', args=[1]),
            '/notifications/mark-as-read/1/',
        )
        self.assertEqual(reverse('notification_mark_all_as_read'), '/notifications/mark-all-as-read/')
        self.assertEqual(reverse('notification_list'), '/notifications/')