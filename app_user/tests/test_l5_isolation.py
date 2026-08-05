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
    """回归：ProjectAccessMixin 的协同成员穿透合并（distinct ∪ 非 distinct）不应抛 TypeError。"""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="研发部")
        ModuleAccessConfig.objects.create(
            module_code='project',
            module_name='项目管理中心',
            enforce_dept_isolation=False,
            enforce_group_isolation=True,   # 开启 L5 → super().get_queryset() 返回 .distinct()
        )

        cls.member_user = User.objects.create_user(
            username='member_user', email='member@x.com', password='x', department=cls.dept)
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

    def test_member_penetration_union_no_typeerror(self):
        """L5 开启时，成员穿透的 distinct|非distinct 合并不再抛 TypeError。"""
        qs = self._qs_for(self.member_user)
        # 无工作组用户走 L5 else 分支 → super() 返回 .distinct() → 触发合并
        self.assertIn(self.membered, qs)  # 作为协同成员可见（仅靠穿透合并）
        self.assertNotIn(self.owned, qs)  # 非负责人、非成员、负责人有组 → 不可见