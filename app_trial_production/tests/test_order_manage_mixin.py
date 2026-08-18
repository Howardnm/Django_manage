"""OrderManageAccessMixin 权限回归测试。

验证工单详情/打印/删除的自定义权限控制：

- 研发工程师（order_manage 角色组）：按 L4 部门隔离查看工单。
- 挤出工程师（extrusion_task 角色组）：可查看所有工单详情/打印，
  跳过 L4 部门隔离（不跨部门被拒）。
- 删除工单由 RndAccessMixin（trial_production.rnd）控制：
  仅研发发起人角色组 + 创建人/超管可删，挤出工程师无权删除。
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app_user.models import Department, ModuleAccessConfig, RoleGroup, UserRole
from app_user.services.identity_service import IdentityService

from app_trial_production.models import ProductionOrder

User = get_user_model()


class OrderManageAccessTests(TestCase):
    """围绕工单详情/打印/删除的 L1 + L4 权限回归。"""

    def setUp(self):
        # ── RBAC 基础数据（与 DB 中 trial_production.* 配置一致）──
        self.rnd = UserRole.objects.create(code='RD_ENGINEER', name='研发工程师')
        self.mgr = UserRole.objects.create(code='RD_MANAGER', name='研发中心管理')
        self.extrusion = UserRole.objects.create(code='EXTRUSION_ENGINEER', name='挤出工程师')

        self.rnd_group = RoleGroup.objects.create(
            code='RND_Center_Engineer_Team', name='研发中心工程师团队')
        self.rnd_group.roles.add(self.rnd)
        self.mgr_group = RoleGroup.objects.create(
            code='RND_Center_management_team', name='研发中心管理团队')
        self.mgr_group.roles.add(self.mgr)
        self.extrusion_group = RoleGroup.objects.create(
            code='Plastic_Extrusion_Engineer_Team', name='塑料挤出工程师团队')
        self.extrusion_group.roles.add(self.extrusion)

        # trial_production.order_manage — 研发角色组，L4 部门隔离开启
        order_cfg = ModuleAccessConfig.objects.create(
            module_code='trial_production.order_manage', module_name='工单管理',
            enforce_dept_isolation=True, enforce_group_isolation=False,
        )
        order_cfg.role_groups.add(self.rnd_group, self.mgr_group)

        # trial_production.extrusion_task — 挤出角色组
        ext_cfg = ModuleAccessConfig.objects.create(
            module_code='trial_production.extrusion_task', module_name='挤出任务',
            enforce_dept_isolation=True, enforce_group_isolation=False,
        )
        ext_cfg.role_groups.add(self.extrusion_group)

        # trial_production.rnd — 研发发起人
        rnd_cfg = ModuleAccessConfig.objects.create(
            module_code='trial_production.rnd', module_name='排产发起/审批',
            enforce_dept_isolation=True, enforce_group_isolation=False,
        )
        rnd_cfg.role_groups.add(self.rnd_group, self.mgr_group)

        IdentityService.invalidate_cache()

        # ── 部门 ──
        self.dept_a = Department.objects.create(name='研发一部')
        self.dept_b = Department.objects.create(name='研发二部')

        # ── 测试用户 ──
        self.creator = self._make_user('creator', self.rnd, self.dept_a)      # 工单创建人（研发一部）
        self.extruder = self._make_user('extruder', self.extrusion, self.dept_b)  # 挤出工程师（研发二部）
        self.other_rnd = self._make_user('other_rnd', self.rnd, self.dept_b)  # 跨部门研发工程师（研发二部）
        self.plain = self._make_user('plain', self.rnd, None)                 # 无部门研发（无工作视野）
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.dev', password='x')

        # ── 测试工单 ──
        self.order = ProductionOrder.objects.create(
            creator=self.creator, code='TP-TEST-01', trial_code='LC-TEST',
            quantity_planned=500, status=ProductionOrder.Status.DRAFT,
        )
        # 挤出工程师自己的工单（挤出操作员=挤出工程师，跨部门）
        self.extruder_order = ProductionOrder.objects.create(
            creator=self.creator, code='TP-TEST-02', trial_code='LC-TEST2',
            quantity_planned=500, status=ProductionOrder.Status.ACCEPTED,
            extruder_operator=self.extruder,
        )

    def _make_user(self, username, role, dept):
        user = User.objects.create_user(
            username=username, email=f'{username}@test.dev', password='x')
        user.user_type = role
        user.department = dept
        user.save()
        return user

    def assert_denied(self, response):
        """非 AJAX 请求被拒 → 302 重定向到 /permission-denied/。"""
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith('/permission-denied/'))

    # ── 详情页：研发工程师 L4 部门隔离 ──

    def test_rnd_same_dept_can_view_detail(self):
        """研发工程师（同部门）查看工单详情 200。"""
        self.client.force_login(self.creator)
        resp = self.client.get(reverse('trial_order_detail', args=[self.order.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_rnd_cross_dept_denied_view_detail(self):
        """研发工程师（跨部门）查看工单详情被拒（L4 部门隔离）。"""
        self.client.force_login(self.other_rnd)
        resp = self.client.get(reverse('trial_order_detail', args=[self.order.pk]))
        self.assert_denied(resp)

    # ── 详情页：挤出工程师跳过 L4/L5 可看所有工单 ──

    def test_extruder_can_view_cross_dept_detail(self):
        """挤出工程师可查看跨部门工单详情（跳过 L4）。"""
        self.client.force_login(self.extruder)
        resp = self.client.get(reverse('trial_order_detail', args=[self.order.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_extruder_can_view_print(self):
        """挤出工程师可打印工单（跳过 L4）。"""
        self.client.force_login(self.extruder)
        resp = self.client.get(reverse('trial_order_print', args=[self.order.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_extruder_own_order_view(self):
        """挤出工程师查看自己作为挤出操作员的工单 200。"""
        self.client.force_login(self.extruder)
        resp = self.client.get(reverse('trial_order_detail', args=[self.extruder_order.pk]))
        self.assertEqual(resp.status_code, 200)

    # ── 详情页：无角色用户被拒 ──

    def test_user_without_any_role_denied(self):
        """无任何模块角色组的用户查看详情被拒。"""
        self.client.force_login(self.plain)
        resp = self.client.get(reverse('trial_order_detail', args=[self.order.pk]))
        self.assert_denied(resp)

    def test_superuser_can_view_any_detail(self):
        """超管查看工单详情 200。"""
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('trial_order_detail', args=[self.order.pk]))
        self.assertEqual(resp.status_code, 200)

    # ── 删除：RndAccessMixin 控制，仅创建人可删 ──

    def test_creator_can_delete_own_draft(self):
        """创建人删除自己的草稿工单成功。"""
        self.client.force_login(self.creator)
        resp = self.client.post(reverse('trial_order_delete', args=[self.order.pk]))
        self.assertIn(resp.status_code, [200, 302])
        self.assertFalse(ProductionOrder.objects.filter(pk=self.order.pk).exists())

    def test_non_creator_rnd_denied_delete(self):
        """研发工程师但非创建人删除草稿被拒（PermissionDenied 硬校验）。"""
        self.client.force_login(self.other_rnd)
        resp = self.client.post(reverse('trial_order_delete', args=[self.order.pk]))
        self.assertIn(resp.status_code, [302, 403])

    def test_extruder_denied_delete(self):
        """挤出工程师删除草稿被拒（无 rnd 权限）。"""
        self.client.force_login(self.extruder)
        resp = self.client.post(reverse('trial_order_delete', args=[self.order.pk]))
        self.assertIn(resp.status_code, [302, 403])
        self.assertTrue(ProductionOrder.objects.filter(pk=self.order.pk).exists())

    def test_creator_cannot_delete_non_draft(self):
        """创建人不能删除非草稿工单（业务校验）。"""
        self.client.force_login(self.creator)
        resp = self.client.post(reverse('trial_order_delete', args=[self.extruder_order.pk]))
        self.assertIn(resp.status_code, [302, 403])
        self.assertTrue(ProductionOrder.objects.filter(pk=self.extruder_order.pk).exists())
