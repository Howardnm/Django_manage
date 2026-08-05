"""L5 工作组隔离回归测试 — 验证修复 app_user/mixins.py 与 autocomplete_registry.py
的 `manager_id` FieldError bug。

复现场景：开启模块 L5 隔离时，一个「无任何已启用工作组」的用户访问列表页，
会走进 get_queryset() 的 else 分支。旧代码用 `{user_field}_id`(如 manager_id)
过滤中间表 app_user_workgroup（该表指向 User 的列恒为 user_id），导致 FieldError。
"""
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model

from app_user.models import Department, WorkGroup, ModuleAccessConfig
from app_user.mixins import UnifiedAccessMixin
from common_utils.autocomplete_registry import make_autocomplete_access_filter
from app_project.mixins import ProjectAccessMixin
from app_project.models import Project, ProjectMember

User = get_user_model()


class _ProjectView(UnifiedAccessMixin):
    """最小视图：模拟 ProjectListView 的 L5 隔离 queryset 构建。"""
    module_code = 'project'
    queryset = Project.objects.all()


class _AutoCompleteView(UnifiedAccessMixin):
    """供 autocomplete 过滤器测试：module_code=None → 走类属性，跳过 L1 角色门。"""
    module_code = None
    identity_required = []
    enforce_dept_isolation = False
    enforce_group_isolation = True
    user_link_fields = ['manager']


class L5WorkGroupIsolationTest(TestCase):
    """聚焦 L5 工作组隔离的 else 分支（用户无工作组）。"""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="研发部")
        ModuleAccessConfig.objects.create(
            module_code='project',
            module_name='项目',
            enforce_dept_isolation=False,   # 关闭 L4，聚焦 L5
            enforce_group_isolation=True,   # 开启 L5
        )

        cls.owner_no_wg = User.objects.create_user(
            username='owner_no_wg', email='a@x.com', password='x', department=cls.dept)
        cls.owner_with_wg = User.objects.create_user(
            username='owner_with_wg', email='b@x.com', password='x', department=cls.dept)
        cls.viewer_no_wg = User.objects.create_user(
            username='viewer_no_wg', email='c@x.com', password='x', department=cls.dept)
        cls.superuser = User.objects.create_superuser(
            username='su', email='su@x.com', password='x')

        cls.wg = WorkGroup.objects.create(name="组A", department=cls.dept, is_active=True)
        cls.wg.members.add(cls.owner_with_wg)

        cls.p_no_wg = Project.objects.create(code='P1', name='无组负责人项目', manager=cls.owner_no_wg)
        cls.p_with_wg = Project.objects.create(code='P2', name='有组负责人项目', manager=cls.owner_with_wg)

    def _queryset_for(self, user):
        view = _ProjectView()
        view.request = RequestFactory().get('/')
        view.request.user = user
        return view.get_queryset()

    def test_no_fielderror_for_no_workgroup_user(self):
        """回归核心：无工作组用户不应抛 FieldError。"""
        qs = self._queryset_for(self.viewer_no_wg)
        self.assertIn(self.p_no_wg, qs)       # 负责人无组 → 可见
        self.assertNotIn(self.p_with_wg, qs)  # 负责人有组且非本人 → 不可见

    def test_owner_with_workgroup_sees_own_and_same_wg(self):
        # 视图用户有工作组 → 走 if 分支：本人负责 或 负责人与自己同组
        qs = self._queryset_for(self.owner_with_wg)
        self.assertIn(self.p_with_wg, qs)  # 本人负责
        self.assertNotIn(self.p_no_wg, qs)  # 负责人无组，不在本人工作组 → 不可见

    def test_superuser_bypasses_isolation(self):
        qs = self._queryset_for(self.superuser)
        self.assertEqual(qs.count(), 2)

    # ── autocomplete_registry.py 的同款 else 分支（第 2 处修复）──
    def test_autocomplete_filter_no_fielderror_for_no_workgroup_user(self):
        access_filter = make_autocomplete_access_filter(_AutoCompleteView)
        qs = access_filter(self.viewer_no_wg, Project.objects.all())
        self.assertIn(self.p_no_wg, qs)       # 负责人无组 → 可见
        self.assertNotIn(self.p_with_wg, qs)  # 负责人有组且非本人 → 不可见


class ProjectAccessUnionTest(TestCase):
    """回归：ProjectAccessMixin 的协同成员穿透合并（distinct ∪ 非 distinct）不应抛 TypeError。

    super().get_queryset() 的 distinct 状态随场景变化：
      - 超管路径：直接返回 qs（非 distinct）
      - 非超管 + L5 开：返回 .distinct()
      - 非超管 + L5 关：返回非 distinct
    无论哪种，`|` 合并两侧都须 distinct 状态一致。
    """

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="研发部")
        cls.cfg = ModuleAccessConfig.objects.create(
            module_code='project',
            module_name='项目管理中心',
            enforce_dept_isolation=False,
            enforce_group_isolation=True,
        )

        cls.member_user = User.objects.create_user(
            username='member_user', email='member@x.com', password='x', department=cls.dept)
        cls.admin = User.objects.create_superuser(
            username='admin', email='admin@x.com', password='x')
        cls.owner = User.objects.create_user(
            username='owner', email='owner@x.com', password='x', department=cls.dept)

        # 让 owner 加入工作组 → L5 会排除其负责的项目，仅靠协同成员穿透才能看到
        wg = WorkGroup.objects.create(name="组A", department=cls.dept, is_active=True)
        wg.members.add(cls.owner)

        cls.owned = Project.objects.create(code='PO', name='负责人项目', manager=cls.owner)
        cls.membered = Project.objects.create(code='PM', name='协同成员项目', manager=cls.owner)
        ProjectMember.objects.create(project=cls.membered, user=cls.member_user)

    def _qs_for(self, user):
        view = ProjectAccessMixin()
        view.queryset = Project.objects.all()  # 模拟 ProjectListView 注入 queryset
        view.request = RequestFactory().get('/')
        view.request.user = user
        return view.get_queryset()

    def _set_l5(self, enabled):
        self.cfg.enforce_group_isolation = enabled
        self.cfg.save(update_fields=['enforce_group_isolation'])
        from app_user.services.identity_service import IdentityService
        IdentityService.invalidate_cache()

    def test_union_no_typeerror_all_combinations(self):
        """L5 开/关 × 超管/非超管 四种组合都不应抛 TypeError。"""
        from app_user.services.identity_service import IdentityService

        # 1) L5 关 + 非超管（super() 返回非 distinct）
        self._set_l5(False)
        IdentityService.invalidate_cache()
        qs = self._qs_for(self.member_user)
        self.assertIn(self.membered, qs)  # 成员穿透可见
        self.assertIn(self.owned, qs)     # L5 关闭 → 全部可见

        # 2) L5 关 + 超管（super() 返回非 distinct）
        qs = self._qs_for(self.admin)
        self.assertEqual(qs.count(), 2)

        # 3) L5 开 + 非超管无工作组（super() 返回 .distinct()）
        self._set_l5(True)
        IdentityService.invalidate_cache()
        qs = self._qs_for(self.member_user)
        self.assertIn(self.membered, qs)  # 仅靠成员穿透合并可见
        self.assertNotIn(self.owned, qs)  # 负责人有组、非成员 → 不可见

        # 4) L5 开 + 超管（super() 返回非 distinct，因超管绕过隔离）
        qs = self._qs_for(self.admin)
        self.assertEqual(qs.count(), 2)


class LevelBypassTest(TestCase):
    """泛化：L4/L5 隔离的「等级跳过」门槛（可后台配置）。"""

    @classmethod
    def setUpTestData(cls):
        cls.deptA = Department.objects.create(name="研发部")
        cls.deptB = Department.objects.create(name="市场部")
        cls.cfg = ModuleAccessConfig.objects.create(
            module_code='project_bypass_test',
            module_name='项目(等级跳过测试)',
            enforce_dept_isolation=True,
            enforce_group_isolation=True,
        )
        # 默认不配置任何跳过门槛

        cls.ownerA = User.objects.create_user(
            username='owner_a', email='oa@x.com', password='x', department=cls.deptA)
        cls.wgA = WorkGroup.objects.create(name="组A", department=cls.deptA, is_active=True)
        cls.wgA.members.add(cls.ownerA)

        cls.low_user = User.objects.create_user(
            username='low', email='low@x.com', password='x', department=cls.deptA, user_level=10)
        cls.mid_user = User.objects.create_user(
            username='mid', email='mid@x.com', password='x', department=cls.deptA, user_level=15)
        cls.high_user = User.objects.create_user(
            username='high', email='high@x.com', password='x', department=cls.deptB, user_level=20)
        # 15 级但在另一个部门 → 用于验证「未到 L4 门槛时仍受部门限制」
        cls.cross_mid_user = User.objects.create_user(
            username='cross_mid', email='cm@x.com', password='x', department=cls.deptB, user_level=15)

        # pA1: 负责人 ownerA 在 deptA 且属于工作组 → 低等级同部门无组用户看不到它
        cls.pA1 = Project.objects.create(code='PA1', name='A部门有组项目', manager=cls.ownerA)

    def _apply_config(self, **kwargs):
        self.cfg.enforce_dept_isolation = kwargs.get('l4', True)
        self.cfg.enforce_group_isolation = kwargs.get('l5', True)
        self.cfg.l4_bypass_min_level = kwargs.get('l4_bypass')
        self.cfg.l5_bypass_min_level = kwargs.get('l5_bypass')
        self.cfg.save()
        from app_user.services.identity_service import IdentityService
        IdentityService.invalidate_cache()

    def _qs(self, user):
        view = UnifiedAccessMixin()
        view.module_code = 'project_bypass_test'
        view.queryset = Project.objects.all()
        view.request = RequestFactory().get('/')
        view.request.user = user
        return view.get_queryset()

    def _can_access(self, user, obj):
        view = UnifiedAccessMixin()
        view.module_code = 'project_bypass_test'
        view.request = RequestFactory().get('/')
        view.request.user = user
        return view.check_object_permission(obj)

    # ── L5 跳过 ──
    def test_l5_bypass_high_level_sees_others_workgroup_record(self):
        self._apply_config(l5_bypass=15)
        # 15 级同部门、无组用户 → 跳过 L5 → 能看到负责人有组的 pA1
        self.assertIn(self.pA1, self._qs(self.mid_user))

    def test_l5_no_bypass_low_level_still_restricted(self):
        self._apply_config(l5_bypass=15)
        # 10 级同部门、无组用户 → 未到门槛 → 仍受 L5，看不到负责人有组的 pA1
        self.assertNotIn(self.pA1, self._qs(self.low_user))

    # ── L4 跳过 ──
    def test_l4_bypass_high_level_sees_other_department(self):
        # 为聚焦 L4，同时关闭 L5：20 级不同部门 → 跳过 L4 → 跨部门可见 pA1
        self._apply_config(l4_bypass=20, l5=False)
        self.assertIn(self.pA1, self._qs(self.high_user))

    def test_l4_no_bypass_low_level_other_department_restricted(self):
        self._apply_config(l4_bypass=20, l5=False)
        # 15 级不同部门 → 未到 L4 门槛 → 仍受 L4，看不到他部门 pA1
        self.assertNotIn(self.pA1, self._qs(self.cross_mid_user))

    # ── 层级递进（L4=20 ≥ L5=15）──
    def test_progression_levels(self):
        self._apply_config(l4_bypass=20, l5_bypass=15)
        # 15 级同部门 → 跳过 L5、仍受 L4 → 部门内可见 pA1
        self.assertIn(self.pA1, self._qs(self.mid_user))
        # 20 级不同部门 → 两层都跳过 → 跨部门可见 pA1
        self.assertIn(self.pA1, self._qs(self.high_user))

    # ── 未配置 → 保持原有行为 ──
    def test_unconfigured_preserves_existing_behavior(self):
        self._apply_config(l4_bypass=None, l5_bypass=None)
        # 15 级同部门、无组用户 → L5 生效 → 看不到负责人有组的 pA1（与改造前一致）
        self.assertNotIn(self.pA1, self._qs(self.mid_user))

    # ── 对象级 ──
    def test_object_level_l5_bypass(self):
        self._apply_config(l5_bypass=15)
        # 15 级同部门用户 → 跳过 L5 → 对象级放行
        self.assertTrue(self._can_access(self.mid_user, self.pA1))
        # 10 级同部门用户 → 未到门槛 → 对象级拒绝（L5 工作组不匹配）
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            self._can_access(self.low_user, self.pA1)

    def test_object_level_l4_bypass(self):
        self._apply_config(l4_bypass=20, l5=False)
        # 20 级不同部门 → 跳过 L4 → 对象级放行
        self.assertTrue(self._can_access(self.high_user, self.pA1))
        # 15 级不同部门 → 未到门槛 → 对象级拒绝（L4 部门不匹配）
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            self._can_access(self.cross_mid_user, self.pA1)


class ModuleAccessConfigValidationTest(TestCase):
    """ModuleAccessConfig.clean() 的 L4/L5 跳过等级校验。"""

    def _make(self, l4, l5):
        return ModuleAccessConfig(
            module_code='validation_test', module_name='校验测试',
            enforce_dept_isolation=True, enforce_group_isolation=True,
            l4_bypass_min_level=l4, l5_bypass_min_level=l5,
        )

    def test_l4_less_than_l5_raises(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self._make(10, 15).full_clean()

    def test_l4_equal_l5_ok(self):
        self._make(15, 15).full_clean()  # 不应抛异常

    def test_l4_greater_than_l5_ok(self):
        self._make(20, 15).full_clean()  # 不应抛异常

    def test_single_layer_configured_ok(self):
        self._make(20, None).full_clean()  # 只有 L4
        self._make(None, 15).full_clean()  # 只有 L5

    def test_neither_configured_ok(self):
        self._make(None, None).full_clean()  # 都不启用