"""app_color_center 权限重构回归测试。

背景：本模块原存在三处权限缺陷——三视图均缺 L3 权限码、user_link_fields 与
列表视图模型字段错配导致 L4 隔离静默失效、写路径借用 app_trial_production 的
RndAccessMixin 做项目负责人/成员校验且读/写共用同一视图。本次重构后需回归的契约：

1. L3 权限码真正生效（改造前被跳过）：访问列表/项目页需 view_colormatchingtask，
   提交保存 BOM 需 change_colormatchingtask。
2. 读写分离：ProjectColorView（GET，view_*）与 ProjectColorSaveView（POST，change_*）
   分别继承 ColorCenterReadMixin / ColorCenterWriteMixin 各自控权。
3. 对象级权限收回：删除 RndAccessMixin 调用后，非项目负责人/成员的配色操作员
   （有 L1 角色 + L3 权限码）也能打开项目配色页并提交 BOM——仅靠模块准入把关。
4. BOM 写入路径回归：保存 BOM、回填 filled_by、推进 ColorMatchingTask、成功回跳详情页。
5. 跨项目 POST 仍被业务校验拦截（配方不属于当前项目 → PermissionDenied）。
6. 关闭部门隔离后：配色操作员跨部门可见配色工单，且后端不再有 user_link_field 告警。
7. 表单卡片显隐：无 change_* 写权限的用户浏览配色页时不展示填写表单（退化为
   只读表格或占位提示）；「修改」按钮仅对写权限用户可见。
8. Mixin 结构回归：Read 继承 color_center、Write 独立注册 color_center.write，
   且 Mixin 均不声明 permission_required（L3 由视图层声明）。
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from app_user.models import Department, ModuleAccessConfig, RoleGroup, UserRole
from app_user.services.identity_service import IdentityService

from app_color_center.mixins import (
    ColorCenterAccessMixin, ColorCenterReadMixin, ColorCenterWriteMixin,
)
from app_color_center.models import ColorMatchingTask
from app_formula.models import LabFormula, ColorPowderBOM, ColorPowderBOMEntry
from app_material.models import MaterialType, MaterialLibrary
from app_project.models import Project, ProjectNode
from app_raw_material.models import RawMaterial, RawMaterialType
from app_trial_production.models import ProductionOrder, ProductionOrderFormulaDetail

User = get_user_model()


def _grant(user, *codenames):
    """为测试用户授予 app_color_center 下的 Django 权限码（L3）。"""
    perms = Permission.objects.filter(
        codename__in=codenames, content_type__app_label='app_color_center')
    user.user_permissions.add(*perms)


class ColorCenterAccessTests(TestCase):
    """围绕配色中心三视图 + 读写分离 + 对象级收回的 L1/L3 权限回归。"""

    def setUp(self):
        # ── RBAC 基础数据 ──
        self.color_op = UserRole.objects.create(code='COLOR_OP', name='配色操作员')
        self.sales = UserRole.objects.create(code='SALES', name='销售')

        color_group = RoleGroup.objects.create(
            code='Color_Center_Operators', name='配色中心操作员组')
        color_group.roles.add(self.color_op)

        # 读模块：color_center（关闭部门隔离，配色中心按角色全量可见）
        read_cfg = ModuleAccessConfig.objects.create(
            module_code='color_center', module_name='材料配色中心',
            enforce_dept_isolation=False, enforce_group_isolation=False,
        )
        read_cfg.role_groups.add(color_group)

        # 写模块：color_center.write（独立注册）
        write_cfg = ModuleAccessConfig.objects.create(
            module_code='color_center.write', module_name='材料配色中心-填写',
            enforce_dept_isolation=False, enforce_group_isolation=False,
        )
        write_cfg.role_groups.add(color_group)

        IdentityService.invalidate_cache()

        # ── 部门 ──
        self.dept_a = Department.objects.create(name='配色一部')
        self.dept_b = Department.objects.create(name='配色二部')

        # ── 用户 ──
        self.viewer = self._make_user('viewer', self.color_op, self.dept_a,
                                      'view_colormatchingtask')
        self.writer = self._make_user('writer', self.color_op, self.dept_a,
                                      'view_colormatchingtask', 'change_colormatchingtask')
        self.noperm = self._make_user('noperm', self.color_op, self.dept_a)  # 组内、无 L3 权限码
        self.outsider = self._make_user('outsider', self.sales, self.dept_a,
                                        'view_colormatchingtask', 'change_colormatchingtask')
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.dev', password='x')

        # 项目负责人（非配色操作员，用于验证对象级收回）
        self.project_manager = self._make_user('project_mgr', self.sales, self.dept_b)

        # ── 业务数据 ──
        mt = MaterialType.objects.create(name='PA66基材')
        self.material = MaterialLibrary.objects.create(
            grade_name='PA66-G30', sap_material_code='SAP-CC-01', category=mt)

        self.project = Project.objects.create(
            code='CC-P-001', name='配色测试项目', manager=self.project_manager,
            material=self.material)

        node = ProjectNode.objects.create(
            project=self.project, stage='RND', round=1, order=0, status='DOING')

        # 位于 dept_b 的工单创建人 → 用于验证关闭部门隔离后跨部门可见
        creator_b = self._make_user('creator_b', self.sales, self.dept_b)

        self.formula = LabFormula.objects.create(
            code='CC-F-001', name='配色配方', material_type=mt,
            project=self.project, project_node=node, creator=creator_b)

        self.order = ProductionOrder.objects.create(
            creator=creator_b, code='CC-O-001', trial_code=self.formula.code,
            quantity_planned=100, status=ProductionOrder.Status.EXTRUDING,
            project=self.project)

        ProductionOrderFormulaDetail.objects.create(
            production_order=self.order, formula=self.formula,
            planned_quantity=100, needs_color_matching=True)

        self.task = ColorMatchingTask.objects.create(
            production_order=self.order, status=ColorMatchingTask.Status.PENDING)

    def _make_user(self, username, role, dept, *perms):
        user = User.objects.create_user(
            username=username, email=f'{username}@test.dev', password='x')
        user.user_type = role
        user.department = dept
        user.save()
        if perms:
            _grant(user, *perms)
        return user

    def assert_denied(self, response):
        """非 AJAX 请求被拒 → 302 重定向到 /permission-denied/。"""
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('permission_denied'), response.url)

    def _list_url(self):
        return reverse('color_center:list')

    def _project_list_url(self):
        return reverse('color_center:project_list')

    def _project_url(self):
        return reverse('color_center:project', args=[self.project.pk])

    def _save_url(self):
        return reverse('color_center:project_save', args=[self.project.pk])

    # ── 匿名 / 超管 ──

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(self._list_url())
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('login'), resp.url)

    def test_superuser_access_everything(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self._list_url()).status_code, 200)
        self.assertEqual(self.client.get(self._project_list_url()).status_code, 200)
        self.assertEqual(self.client.get(self._project_url()).status_code, 200)

    # ── L1：角色组闸门 ──

    def test_outsider_denied_even_with_perms(self):
        """非配色角色组用户，即使持有 L3 权限码也被拒（L1 闸门）。"""
        self.client.force_login(self.outsider)
        self.assert_denied(self.client.get(self._list_url()))
        self.assert_denied(self.client.get(self._project_url()))

    # ── L3：权限码真正生效（改造前被跳过）──

    def test_noperm_member_denied(self):
        """组内但无 view_colormatchingtask 权限码 → 列表页被拒（L3 生效）。"""
        self.client.force_login(self.noperm)
        self.assert_denied(self.client.get(self._list_url()))
        self.assert_denied(self.client.get(self._project_list_url()))
        self.assert_denied(self.client.get(self._project_url()))

    def test_viewer_can_read(self):
        """有 view 权限码的角色组成员可访问列表/项目页。"""
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self._list_url()).status_code, 200)
        self.assertEqual(self.client.get(self._project_list_url()).status_code, 200)
        self.assertEqual(self.client.get(self._project_url()).status_code, 200)

    # ── 表单卡片显隐：无写权限不展示填写表单 ──

    def _post_bom(self, user, formula=None):
        """以 user 身份提交一条含单个色粉 entry 的 BOM，返回响应。"""
        raw_type = RawMaterialType.objects.create(name='色粉', code='PIGMENT', order=1)
        raw = RawMaterial.objects.create(
            name='炭黑', model_name='CB-01', category=raw_type)
        self.client.force_login(user)
        return self.client.post(self._save_url(), {
            'formula_id': (formula or self.formula).pk,
            'batch_save_mode': '',
            'remark': '回归测试-表单显隐',
            'entries-TOTAL_FORMS': '1',
            'entries-INITIAL_FORMS': '0',
            'entries-MIN_NUM_FORMS': '0',
            'entries-MAX_NUM_FORMS': '1000',
            'entries-0-feeding_port': '1_MAIN',
            'entries-0-weighing_scale': 'D',
            'entries-0-raw_material': raw.pk,
            'entries-0-percentage': '0.500',
            'entries-0-is_pre_mix': '',
            'entries-0-pre_mix_order': '0',
            'entries-0-pre_mix_time': '0',
        })

    def test_no_bom_no_write_permission_shows_placeholder_not_form(self):
        """配方尚无 BOM 且用户无写权限 → 展示占位提示，不含填写表单。"""
        self.client.force_login(self.viewer)
        resp = self.client.get(self._project_url())
        self.assertEqual(resp.status_code, 200)
        # 表单卡片不应出现
        self.assertNotContains(resp, 'id="bom-form"')
        # 展示「尚未填写」占位提示
        self.assertContains(resp, '尚未填写色粉配比BOM')

    def test_no_bom_write_permission_shows_form(self):
        """配方尚无 BOM 且用户有写权限 → 展示填写表单。"""
        self.client.force_login(self.writer)
        resp = self.client.get(self._project_url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="bom-form"')

    def test_existing_bom_write_permission_needs_edit_to_show_form(self):
        """已填 BOM + 写权限：默认只读表格，?edit=1 才展示表单。"""
        self._post_bom(self.writer)

        self.client.force_login(self.writer)
        resp = self.client.get(self._project_url())
        self.assertEqual(resp.status_code, 200)
        # 未带 edit=1 → 只读表格 + 修改按钮，无表单
        self.assertNotContains(resp, 'id="bom-form"')
        self.assertContains(resp, '修改')

        resp_edit = self.client.get(self._project_url() + '?edit=1')
        self.assertEqual(resp_edit.status_code, 200)
        self.assertContains(resp_edit, 'id="bom-form"')

    def test_existing_bom_no_write_permission_hides_edit_button(self):
        """已填 BOM + 无写权限 → 只读表格可见，但「修改」按钮不展示。"""
        self._post_bom(self.writer)

        self.client.force_login(self.viewer)
        resp = self.client.get(self._project_url())
        self.assertEqual(resp.status_code, 200)
        # 只读表格可见（有 entry 数据）
        self.assertContains(resp, '已填写')
        # 修改按钮不显示（can_write=False）
        self.assertNotContains(resp, '修改')
        self.assertNotContains(resp, 'id="bom-form"')

    # ── 读写分离：写需 change 权限码 ──

    def test_viewer_cannot_post_save(self):
        """仅有 view 权限码（无 change）→ POST 保存被拒。"""
        self.client.force_login(self.viewer)
        resp = self.client.post(self._save_url(), {'formula_id': self.formula.pk})
        self.assert_denied(resp)
        self.assertFalse(ColorPowderBOM.objects.filter(formula=self.formula).exists())

    def test_writer_can_post_save(self):
        """有 change 权限码 → POST 保存成功，写入 BOM 并推进任务。"""
        self.client.force_login(self.writer)
        resp = self.client.post(self._save_url(), {
            'formula_id': self.formula.pk,
            'batch_save_mode': '',
            'remark': '回归测试',
            'entries-TOTAL_FORMS': '0',
            'entries-INITIAL_FORMS': '0',
            'entries-MIN_NUM_FORMS': '0',
            'entries-MAX_NUM_FORMS': '1000',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn(self._project_url(), resp.url)  # 回跳详情页，而非 /save/

        bom = ColorPowderBOM.objects.get(formula=self.formula)
        self.assertEqual(bom.filled_by, self.writer)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, ColorMatchingTask.Status.IN_PROGRESS)
        self.assertEqual(self.task.operator, self.writer)

    # ── 对象级收回：非负责人/成员也可打开配色页 ──

    def test_non_member_can_open_project(self):
        """配色操作员非项目负责人/成员（有 L1+L3）也能打开项目配色页。"""
        self.client.force_login(self.writer)
        # 该项目 manager=project_manager，writer 不是成员
        self.assertNotEqual(self.project.manager_id, self.writer.pk)
        resp = self.client.get(self._project_url())
        self.assertEqual(resp.status_code, 200)

    def test_non_member_can_post_save(self):
        """非负责人/成员的配色操作员也能提交 BOM（对象级不再限制负责人/成员）。"""
        self.client.force_login(self.writer)
        resp = self.client.post(self._save_url(), {
            'formula_id': self.formula.pk,
            'entries-TOTAL_FORMS': '0',
            'entries-INITIAL_FORMS': '0',
            'entries-MIN_NUM_FORMS': '0',
            'entries-MAX_NUM_FORMS': '1000',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ColorPowderBOM.objects.filter(formula=self.formula).exists())

    # ── 关闭部门隔离：跨部门可见 ──

    def test_cross_dept_order_visible_in_list(self):
        """配色操作员（部门A）能看到部门B创建人所属的配色工单（L4 已关闭）。"""
        self.client.force_login(self.viewer)
        resp = self.client.get(self._list_url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.order.code)

    # ── 跨项目 POST 仍被业务校验拦截 ──

    def test_cross_project_post_blocked(self):
        """POST 提交不属于当前项目的配方 → PermissionDenied。"""
        other_manager = self._make_user('other_mgr', self.sales, self.dept_b)
        other = Project.objects.create(
            code='CC-P-002', name='其他项目', manager=other_manager, material=self.material)
        foreign_formula = LabFormula.objects.create(
            code='CC-F-002', name='他项目配方', material_type=self.material.category,
            project=other, creator=self.project_manager)

        self.client.force_login(self.writer)
        resp = self.client.post(self._save_url(), {'formula_id': foreign_formula.pk})
        self.assert_denied(resp)
        self.assertFalse(ColorPowderBOM.objects.filter(formula=foreign_formula).exists())


class ColorCenterMixinStructureTests(TestCase):
    """Mixin 分层结构回归：读继承 color_center、写独立注册 color_center.write。"""

    def test_read_mixin_inherits_base_module_code(self):
        self.assertEqual(ColorCenterReadMixin.module_code, 'color_center')
        self.assertEqual(ColorCenterReadMixin.module_name, '材料配色中心')
        self.assertTrue(issubclass(ColorCenterReadMixin, ColorCenterAccessMixin))

    def test_write_mixin_has_own_module_code(self):
        self.assertEqual(ColorCenterWriteMixin.module_code, 'color_center.write')
        self.assertEqual(ColorCenterWriteMixin.module_name, '材料配色中心-填写')
        self.assertTrue(issubclass(ColorCenterWriteMixin, ColorCenterReadMixin))

    def test_mixins_do_not_override_permission_required(self):
        """permission_required 由视图层声明，Mixin 不写（回退基类默认 []）。"""
        self.assertEqual(ColorCenterReadMixin.permission_required, [])
        self.assertEqual(ColorCenterWriteMixin.permission_required, [])