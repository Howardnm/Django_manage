"""看板工作台只读排产日历 — 回归测试。

覆盖范围:
    1. 路由解析 (scheduling_calendar / scheduling_calendar_events / 原 trial_extrusion_board_events)
    2. 共享序列化函数 build_extrusion_calendar_events（从原事件接口提取）
    3. 原挤出排产工作台事件接口重构后无回归（与原实现输出一致）
    4. 新的只读事件接口（数据与原接口完全一致 / 权限控制）
    5. 只读页面视图（渲染 / 权限控制）
    6. 侧边栏菜单入口（menu_modules 定义 + 同步后位于看板工作台下）
"""
import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from app_trial_production.models import ProductionOrder
from app_trial_production.services.extrusion_service import build_extrusion_calendar_events

User = get_user_model()


def _make_scheduled_order(code, start, end=None, status=ProductionOrder.Status.ACCEPTED, **kwargs):
    """构造一个已排产工单。"""
    return ProductionOrder.objects.create(
        creator=User.objects.first(),
        code=code,
        trial_code=f'LC-{code}',
        quantity_planned=500,
        status=status,
        extrusion_scheduled_date=start,
        extrusion_scheduled_end=end or start,
        **kwargs,
    )


class UrlReverseTests(TestCase):
    """路由解析回归。"""

    def test_readonly_page_url(self):
        self.assertEqual(reverse('scheduling_calendar'), '/scheduling-calendar/')

    def test_readonly_events_url(self):
        self.assertEqual(reverse('scheduling_calendar_events'), '/scheduling-calendar/events/')

    def test_original_board_events_url_still_resolves(self):
        """原排产工作台事件接口未被破坏。"""
        self.assertEqual(
            reverse('trial_extrusion_board_events'),
            '/trial-production/extrusion-board/events/',
        )


class BuildEventsFunctionTests(TestCase):
    """共享序列化函数回归（提取自 ExtrusionEventsApiView）。"""

    def setUp(self):
        self.user = User.objects.create_superuser(username='admin', email='a@t.dev', password='x')
        self.start = timezone.now() - timezone.timedelta(days=7)
        self.end = timezone.now() + timezone.timedelta(days=7)
        self.range_start = self.start.isoformat()
        self.range_end = self.end.isoformat()

    def test_no_scheduled_orders_returns_empty(self):
        self.assertEqual(build_extrusion_calendar_events(self.range_start, self.range_end), [])

    def test_scheduled_order_produces_valid_event(self):
        order = _make_scheduled_order('TP-1', timezone.now())
        events = build_extrusion_calendar_events(self.range_start, self.range_end)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev['id'], str(order.pk))
        self.assertEqual(ev['title'], order.code)
        self.assertIn('start', ev)
        self.assertIn('end', ev)
        self.assertIn('allDay', ev)
        self.assertIn('editable', ev)
        # 关键字段齐全
        for key in ('trial_code', 'quantity', 'formula_count', 'needs_color',
                    'project_name', 'process_profile_name', 'created_at',
                    'material_type_name', 'rgb_value'):
            self.assertIn(key, ev['extendedProps'])

    def test_out_of_range_order_excluded(self):
        """范围过滤：排期在查询窗口外的工单不返回。"""
        past = self.start - timezone.timedelta(days=100)
        _make_scheduled_order('TP-old', past)
        events = build_extrusion_calendar_events(self.range_start, self.range_end)
        self.assertEqual(events, [])

    def test_empty_range_returns_all(self):
        """不传 start/end 时不按范围过滤。"""
        _make_scheduled_order('TP-all', timezone.now())
        events = build_extrusion_calendar_events('', '')
        self.assertEqual(len(events), 1)

    def test_invalid_range_ignored(self):
        """非法时间范围不报错，退化为不过滤。"""
        order = _make_scheduled_order('TP-bad', timezone.now())
        events = build_extrusion_calendar_events('bogus', 'also-bogus')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['id'], str(order.pk))

    def test_allday_event_uses_date_format(self):
        """全天事件 start/end 为纯日期，且长度为 10（YYYY-MM-DD）。"""
        local_tz = timezone.get_current_timezone()
        start = timezone.localtime(timezone.now(), local_tz).replace(
            hour=0, minute=0, second=0, microsecond=0)
        _make_scheduled_order('TP-day', start, status=ProductionOrder.Status.EXTRUDING)
        events = build_extrusion_calendar_events(
            (start - timezone.timedelta(days=1)).isoformat(),
            (start + timezone.timedelta(days=1)).isoformat(),
        )
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]['allDay'])
        self.assertEqual(len(events[0]['start']), 10)
        self.assertEqual(len(events[0]['end']), 10)


class OriginalBoardEventsEndpointTests(TestCase):
    """原排产工作台事件接口重构回归：输出应与共享函数一致。"""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin', email='a@t.dev', password='x')
        self.client.force_login(self.superuser)
        self.start = (timezone.now() - timezone.timedelta(days=7)).isoformat()
        self.end = (timezone.now() + timezone.timedelta(days=7)).isoformat()

    def test_anonymous_redirected(self):
        self.client.logout()
        resp = self.client.get(reverse('trial_extrusion_board_events'))
        self.assertIn(resp.status_code, [302, 403])

    def test_returns_events_for_superuser(self):
        _make_scheduled_order('BOARD-1', timezone.now())
        resp = self.client.get(
            reverse('trial_extrusion_board_events'),
            {'start': self.start, 'end': self.end},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['title'], 'BOARD-1')

    def test_output_matches_shared_function(self):
        """重构后接口输出与 build_extrusion_calendar_events 完全一致。"""
        _make_scheduled_order('BOARD-parity', timezone.now())
        endpoint = self.client.get(
            reverse('trial_extrusion_board_events'),
            {'start': self.start, 'end': self.end},
        ).json()
        direct = build_extrusion_calendar_events(self.start, self.end)
        self.assertEqual(endpoint, direct)


class ReadonlyEventsEndpointTests(TestCase):
    """新只读事件接口：数据一致性 + 权限。"""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin', email='a@t.dev', password='x')
        self.start = (timezone.now() - timezone.timedelta(days=7)).isoformat()
        self.end = (timezone.now() + timezone.timedelta(days=7)).isoformat()

    def test_anonymous_redirected(self):
        resp = self.client.get(reverse('scheduling_calendar_events'))
        self.assertIn(resp.status_code, [302, 403])

    def test_superuser_returns_events(self):
        self.client.force_login(self.superuser)
        _make_scheduled_order('RO-1', timezone.now())
        resp = self.client.get(
            reverse('scheduling_calendar_events'),
            {'start': self.start, 'end': self.end},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_regular_user_without_panel_role_denied(self):
        """无 panel 权限的普通用户被拒绝（PanelAccessMixin 生效）。"""
        dummy = User.objects.create_user(username='plain', password='x')
        self.client.force_login(dummy)
        resp = self.client.get(reverse('scheduling_calendar_events'))
        self.assertIn(resp.status_code, [302, 403])

    def test_parity_with_board_endpoint(self):
        """只读接口与原工作台接口返回相同事件数据。"""
        self.client.force_login(self.superuser)
        _make_scheduled_order('RO-parity', timezone.now())
        ro = self.client.get(
            reverse('scheduling_calendar_events'),
            {'start': self.start, 'end': self.end},
        ).json()
        board = self.client.get(
            reverse('trial_extrusion_board_events'),
            {'start': self.start, 'end': self.end},
        ).json()
        self.assertEqual(ro, board)


class ReadonlyPageViewTests(TestCase):
    """只读页面视图：渲染 + 权限。"""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin', email='a@t.dev', password='x')

    def test_anonymous_redirected(self):
        resp = self.client.get(reverse('scheduling_calendar'))
        self.assertIn(resp.status_code, [302, 403])

    def test_regular_user_without_panel_role_denied(self):
        dummy = User.objects.create_user(username='plain', password='x')
        self.client.force_login(dummy)
        resp = self.client.get(reverse('scheduling_calendar'))
        self.assertIn(resp.status_code, [302, 403])

    def test_superuser_page_renders_calendar(self):
        self.client.force_login(self.superuser)
        resp = self.client.get(reverse('scheduling_calendar'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('id="scheduling-calendar"', content)
        self.assertIn('fullcalendar', content)
        self.assertIn('scheduling_calendar.js', content)
        self.assertIn('scheduling_calendar.css', content)
        # 只读页面不应注入任何排期写操作 URL
        self.assertNotIn('SCHEDULE_URL', content)
        self.assertNotIn('UNSCHEDULE_URL_PREFIX', content)


class SidebarMenuTests(TestCase):
    """侧边栏菜单入口回归。"""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin', email='a@t.dev', password='x')

    def test_menu_definition_contains_readonly_calendar(self):
        """menu_modules.get_dashboard() 代码定义含「排产日历」子项（sync_menus 数据源）。"""
        from app_user.services.menu_modules import MenuModule
        dash = MenuModule.get_dashboard()
        names = [s['name'] for s in dash['sub_items']]
        self.assertIn('排产日历', names)
        sub = next(s for s in dash['sub_items'] if s['name'] == '排产日历')
        self.assertEqual(sub['url_name'], 'scheduling_calendar')

    def test_synced_subitem_lives_under_dashboard_module(self):
        """按 sync_menus 的写入形态自建数据，验证挂在「看板工作台」下且可被菜单服务渲染。"""
        from app_user.models import SidebarModule, SidebarSubItem
        from app_user.services.menu_service import MenuService

        # 模拟 sync_menus 对 get_dashboard() 的写入结果
        dash = SidebarModule.objects.create(
            code='dashboard', name='看板工作台', icon='smart-home',
            url_name='panel_home', module_access=None, sort_order=0,
        )
        SidebarSubItem.objects.create(
            module=dash, name='排产日历',
            url_name='scheduling_calendar', permissions=[],
        )
        sub = SidebarSubItem.objects.get(module=dash, name='排产日历')
        self.assertEqual(sub.url_name, 'scheduling_calendar')

        # 超管菜单应渲染出该子项且激活态正确
        class R:
            user = self.superuser
            resolver_match = type('RM', (), {'view_name': 'scheduling_calendar'})()

        menu = MenuService.get_user_menu(R())
        dash_rendered = next((m for m in menu if m['name'] == '看板工作台'), None)
        self.assertIsNotNone(dash_rendered)
        names = [s['name'] for s in dash_rendered['sub_items']]
        self.assertIn('排产日历', names)
        active = next(s for s in dash_rendered['sub_items'] if s['name'] == '排产日历')
        self.assertTrue(active['is_active'])