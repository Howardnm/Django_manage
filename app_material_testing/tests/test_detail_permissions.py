"""测试任务详情页独立权限 Mixin 回归测试。

验证 TestingDetailAccessMixin：
1. 数据所有者 = 测试任务关联项目的负责人（production_order.project.manager），
   而非 assigned_to（测试员）。
2. 研发角色组（material_testing 授权、非 team）：按项目负责人做 L4 部门隔离。
3. 测试中心人员（命中 material_testing.team）：跳过 L4/L5，可见全部任务。
4. 无 view_testingtask 权限码 → 拒绝。
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from app_user.models import Department, ModuleAccessConfig, RoleGroup, UserRole
from app_user.services.identity_service import IdentityService

from app_material.models import MaterialType
from app_formula.models import LabFormula
from app_project.models import Project, ProjectNode
from app_trial_production.models import ProductionOrder, ProductionOrderFormulaDetail
from app_material_testing.models import TestingTask
from app_material_testing.mixins import (
    TestingAccessMixin, TestingTeamAccessMixin, TestingDetailAccessMixin,
)

User = get_user_model()


def _grant(user, *codenames):
    perms = Permission.objects.filter(
        codename__in=codenames, content_type__app_label='app_material_testing')
    user.user_permissions.add(*perms)


class TestingDetailAccessTests(TestCase):
    """详情页权限：研发按项目负责人隔离、测试中心人员跳过 L4/L5。"""

    def setUp(self):
        # ── RBAC：角色 + 角色组 ──
        self.rnd_role = UserRole.objects.create(code='RD_ENGINEER', name='研发工程师')
        self.testing_role = UserRole.objects.create(code='TESTING_OPERATOR', name='测试操作员')

        self.rnd_group = RoleGroup.objects.create(
            code='RND_Center_Engineer_Team', name='研发中心工程师团队')
        self.rnd_group.roles.add(self.rnd_role)
        self.testing_group = RoleGroup.objects.create(
            code='Testing_Center_Team', name='测试中心团队')
        self.testing_group.roles.add(self.testing_role)

        # material_testing — 同时配研发 + 测试中心角色组，L4 隔离开
        main_cfg = ModuleAccessConfig.objects.create(
            module_code='material_testing', module_name='材料测试中心',
            enforce_dept_isolation=True, enforce_group_isolation=False,
        )
        main_cfg.role_groups.add(self.rnd_group, self.testing_group)

        # material_testing.team — 仅测试中心角色组（身份标识）
        team_cfg = ModuleAccessConfig.objects.create(
            module_code='material_testing.team', module_name='材料测试中心-团队成员',
            enforce_dept_isolation=True, enforce_group_isolation=False,
        )
        team_cfg.role_groups.add(self.testing_group)

        IdentityService.invalidate_cache()

        # ── 部门 ──
        self.dept_a = Department.objects.create(name='研发一部')
        self.dept_b = Department.objects.create(name='研发二部')

        # ── 用户 ──
        self.pm_dept_a = self._make_user('pm_a', self.rnd_role, self.dept_a,
                                         'view_testingtask')
        self.rnd_dept_a = self._make_user('rnd_a', self.rnd_role, self.dept_a,
                                          'view_testingtask')
        self.rnd_dept_b = self._make_user('rnd_b', self.rnd_role, self.dept_b,
                                          'view_testingtask')
        self.testing_op = self._make_user('testing_op', self.testing_role, self.dept_b,
                                          'view_testingtask')
        self.no_perm = self._make_user('no_perm', self.rnd_role, self.dept_a)
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.dev', password='x')

        # ── 业务数据：项目归 dept_a 负责人，测试任务 assigned_to 是 dept_b 测试员 ──
        mt = MaterialType.objects.create(name='PA66')
        self.project = Project.objects.create(
            code='MT-P-001', name='测试项目', manager=self.pm_dept_a)
        self.node = ProjectNode.objects.create(
            project=self.project, stage='RND', round=1, order=0, status='DOING')
        formula = LabFormula.objects.create(
            code='MT-F-001', name='配方', material_type=mt,
            project=self.project, project_node=self.node, creator=self.rnd_dept_a)
        self.order = ProductionOrder.objects.create(
            creator=self.rnd_dept_a, code='MT-O-001', trial_code='MT-F-001',
            status=ProductionOrder.Status.TESTING, project=self.project)
        ProductionOrderFormulaDetail.objects.create(
            production_order=self.order, formula=formula, planned_quantity=100)
        # assigned_to = dept_b 测试员（用于证明隔离不再以 assigned_to 为所有者）
        self.task = TestingTask.objects.create(
            production_order=self.order, assigned_to=self.testing_op,
            status=TestingTask.Status.IN_PROGRESS)

    def _make_user(self, username, role, dept=None, *perms):
        user = User.objects.create_user(
            username=username, email=f'{username}@test.local', password='x')
        user.user_type = role
        if dept:
            user.department = dept
        user.save()
        if perms:
            _grant(user, *perms)
        return user

    def _detail_url(self):
        return reverse('material_testing:detail', args=[self.task.pk])

    def assert_denied(self, response):
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith('/permission-denied/'))

    # ── 研发工程师：按项目负责人部门隔离 ──

    def test_rnd_same_dept_as_project_manager_can_view(self):
        """研发工程师与项目负责人同部门 → 详情页 200。"""
        self.client.force_login(self.rnd_dept_a)
        resp = self.client.get(self._detail_url())
        self.assertEqual(resp.status_code, 200)

    def test_rnd_cross_dept_from_project_manager_denied(self):
        """研发工程师跨项目负责人部门 → 详情页被拒（L4）。"""
        self.client.force_login(self.rnd_dept_b)
        resp = self.client.get(self._detail_url())
        self.assert_denied(resp)

    def test_project_manager_self_can_view(self):
        """项目负责人本人 → 详情页 200。"""
        self.client.force_login(self.pm_dept_a)
        resp = self.client.get(self._detail_url())
        self.assertEqual(resp.status_code, 200)

    # ── 测试中心人员：跳过 L4/L5 ──

    def test_testing_team_cross_dept_can_view(self):
        """测试中心人员跨部门（相对项目负责人）→ 详情页 200（跳过 L4）。"""
        self.client.force_login(self.testing_op)
        resp = self.client.get(self._detail_url())
        self.assertEqual(resp.status_code, 200)

    # ── 权限码 / 超管 ──

    def test_no_view_permission_denied(self):
        """无 view_testingtask 权限码 → 详情页被拒。"""
        self.client.force_login(self.no_perm)
        resp = self.client.get(self._detail_url())
        self.assert_denied(resp)

    def test_superuser_can_view(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self._detail_url())
        self.assertEqual(resp.status_code, 200)


class TestingDetailMixinUnitTests(TestCase):
    """Mixin 层单元回归：owner 解析 + 身份归属。"""

    def setUp(self):
        self.dept = Department.objects.create(name='研发部')
        self.rnd_role = UserRole.objects.create(code='RD_ENGINEER', name='研发工程师')
        self.testing_role = UserRole.objects.create(code='TESTING_OPERATOR', name='测试操作员')
        self.rnd_group = RoleGroup.objects.create(code='RND_Team', name='研发团队')
        self.rnd_group.roles.add(self.rnd_role)
        self.testing_group = RoleGroup.objects.create(code='Testing_Team', name='测试团队')
        self.testing_group.roles.add(self.testing_role)

        main_cfg = ModuleAccessConfig.objects.create(
            module_code='material_testing', module_name='材料测试中心',
            enforce_dept_isolation=True, enforce_group_isolation=False)
        main_cfg.role_groups.add(self.rnd_group, self.testing_group)
        team_cfg = ModuleAccessConfig.objects.create(
            module_code='material_testing.team', module_name='材料测试中心-团队成员',
            enforce_dept_isolation=True, enforce_group_isolation=False)
        team_cfg.role_groups.add(self.testing_group)
        IdentityService.invalidate_cache()

        self.pm = self._make_user('pm', self.rnd_role, self.dept)
        self.testing = self._make_user('testing', self.testing_role, self.dept)

        mt = MaterialType.objects.create(name='PA66')
        self.project = Project.objects.create(name='项目', manager=self.pm)
        node = ProjectNode.objects.create(
            project=self.project, stage='RND', round=1, order=0, status='DOING')
        formula = LabFormula.objects.create(
            code='F', name='配方', material_type=mt,
            project=self.project, project_node=node, creator=self.pm)
        order = ProductionOrder.objects.create(
            creator=self.pm, code='O', trial_code='F',
            status=ProductionOrder.Status.TESTING, project=self.project)
        ProductionOrderFormulaDetail.objects.create(
            production_order=order, formula=formula, planned_quantity=100)
        self.task = TestingTask.objects.create(
            production_order=order, assigned_to=self.testing,
            status=TestingTask.Status.IN_PROGRESS)

        self.mixin = TestingDetailAccessMixin()
        self.mixin.user_link_fields = ['assigned_to']

    def _make_user(self, username, role, dept):
        user = User.objects.create_user(
            username=username, email=f'{username}@test.local', password='x')
        user.user_type = role
        user.department = dept
        user.save()
        return user

    def test_resolve_owner_returns_project_manager(self):
        """_resolve_owner 返回项目负责人，而非 assigned_to（测试员）。"""
        owner = self.mixin._resolve_owner(self.task)
        self.assertEqual(owner, self.pm)
        self.assertNotEqual(owner, self.testing)

    def test_resolve_owner_returns_none_without_order(self):
        """无 production_order 时 owner 为 None。"""
        orphan = TestingTask(status=TestingTask.Status.PENDING)
        self.assertIsNone(self.mixin._resolve_owner(orphan))

    def test_team_mixin_identity_codes(self):
        """模块码归属正确。"""
        self.assertEqual(TestingAccessMixin.module_code, 'material_testing')
        self.assertEqual(TestingTeamAccessMixin.module_code, 'material_testing.team')
        self.assertEqual(TestingDetailAccessMixin.module_code, 'material_testing')