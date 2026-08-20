"""色粉配比 BOM 保存回归测试。

覆盖本轮两项改动：

1. 空表校验：保存「配色 BOM」时，若明细表格全部为空（0 行、全空白行、或全部被
   标记删除），formset 拒绝提交，不落库空 BOM，也不推进 ColorMatchingTask。
2. 入口与跳转：
   - fill.html 的「尚未填写色粉配比BOM」卡片在有写权限时补「填写」按钮（?edit=1）；
   - 任务/项目列表的「填写配色」按钮仅在存在未填 BOM 时显示，且跳转参数指向首个
     未填配方（stage/round/formula_id 完整）。
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from app_user.models import Department, ModuleAccessConfig, RoleGroup, UserRole
from app_user.services.identity_service import IdentityService

from app_color_center.models import ColorMatchingTask
from app_color_center.views import _first_unfilled_formula, _fill_redirect_params
from app_formula.models import LabFormula, ColorPowderBOM, ColorPowderBOMEntry
from app_material.models import MaterialType, MaterialLibrary
from app_project.models import Project, ProjectNode
from app_raw_material.models import RawMaterial, RawMaterialType
from app_trial_production.models import ProductionOrder, ProductionOrderFormulaDetail

User = get_user_model()


def _grant(user, *codenames):
    perms = Permission.objects.filter(
        codename__in=codenames, content_type__app_label='app_color_center')
    user.user_permissions.add(*perms)


class BOMSaveBase(TestCase):
    """公共 setUp：搭建 RBAC + 项目/配方/工单/配色任务 全链路。"""

    def setUp(self):
        # ── RBAC 基础数据 ──
        self.color_op = UserRole.objects.create(code='COLOR_OP', name='配色操作员')
        self.sales = UserRole.objects.create(code='SALES', name='销售')

        color_group = RoleGroup.objects.create(
            code='Color_Center_Operators', name='配色中心操作员组')
        color_group.roles.add(self.color_op)

        read_cfg = ModuleAccessConfig.objects.create(
            module_code='color_center', module_name='材料配色中心',
            enforce_dept_isolation=False, enforce_group_isolation=False,
        )
        read_cfg.role_groups.add(color_group)

        write_cfg = ModuleAccessConfig.objects.create(
            module_code='color_center.write', module_name='材料配色中心-填写',
            enforce_dept_isolation=False, enforce_group_isolation=False,
        )
        write_cfg.role_groups.add(color_group)
        IdentityService.invalidate_cache()

        self.dept = Department.objects.create(name='配色一部')

        self.viewer = self._make_user('viewer', self.color_op, 'view_colormatchingtask')
        self.writer = self._make_user(
            'writer', self.color_op, 'view_colormatchingtask', 'change_colormatchingtask')

        # ── 业务数据 ──
        mt = MaterialType.objects.create(name='PA66基材')
        self.material = MaterialLibrary.objects.create(
            grade_name='PA66-G30', sap_material_code='SAP-BOMT-01', category=mt)

        mgr = self._make_user('mgr', self.sales)
        self.project = Project.objects.create(
            code='BOMT-P-001', name='BOM回归项目', manager=mgr, material=self.material)

        self.node = ProjectNode.objects.create(
            project=self.project, stage='RND', round=1, order=0, status='DOING')

        creator = self._make_user('creator', self.sales)
        self.formula = LabFormula.objects.create(
            code='BOMT-F-001', name='回归配方', material_type=mt,
            project=self.project, project_node=self.node, creator=creator)

        self.order = ProductionOrder.objects.create(
            creator=creator, code='BOMT-O-001', trial_code=self.formula.code,
            quantity_planned=100, status=ProductionOrder.Status.EXTRUDING,
            project=self.project)

        ProductionOrderFormulaDetail.objects.create(
            production_order=self.order, formula=self.formula,
            planned_quantity=100, needs_color_matching=True)

        self.task = ColorMatchingTask.objects.create(
            production_order=self.order, status=ColorMatchingTask.Status.PENDING)

        # 供有效明细行使用的原材料
        raw_type = RawMaterialType.objects.create(name='色粉', code='PIGMENT', order=1)
        self.raw = RawMaterial.objects.create(
            name='炭黑', model_name='CB-01', category=raw_type)

    def _make_user(self, username, role, *perms):
        user = User.objects.create_user(
            username=username, email=f'{username}@test.dev', password='x')
        user.user_type = role
        user.department = self.dept
        user.save()
        if perms:
            _grant(user, *perms)
        return user

    # ── URL ──
    def _project_url(self):
        return reverse('color_center:project', args=[self.project.pk])

    def _save_url(self):
        return reverse('color_center:project_save', args=[self.project.pk])

    def _list_url(self):
        return reverse('color_center:list')

    def _project_list_url(self):
        return reverse('color_center:project_list')

    # ── POST 数据构造 ──
    def _entry_fields(self, idx, raw_pk):
        """构造第 idx 行明细的 POST 字段（有效行）。"""
        return {
            f'entries-{idx}-feeding_port': '1_MAIN',
            f'entries-{idx}-weighing_scale': 'D',
            f'entries-{idx}-raw_material': str(raw_pk),
            f'entries-{idx}-percentage': '0.500',
            f'entries-{idx}-is_pre_mix': '',
            f'entries-{idx}-pre_mix_order': '0',
            f'entries-{idx}-pre_mix_time': '0',
        }

    def _blank_entry_fields(self, idx):
        """构造第 idx 行明细的 POST 字段（全空白行）。"""
        return {
            f'entries-{idx}-feeding_port': '1_MAIN',
            f'entries-{idx}-weighing_scale': 'D',
            f'entries-{idx}-raw_material': '',
            f'entries-{idx}-percentage': '',
            f'entries-{idx}-is_pre_mix': '',
            f'entries-{idx}-pre_mix_order': '',
            f'entries-{idx}-pre_mix_time': '',
        }

    def _post_bom(self, total_forms=1, entry_fields=None, delete_flags=None,
                  batch_save_mode='', user=None):
        """提交 BOM：默认 1 行有效明细；可指定行数/字段/删除标记/批量模式。"""
        data = {
            'formula_id': self.formula.pk,
            'batch_save_mode': batch_save_mode,
            'remark': '回归测试',
            'entries-TOTAL_FORMS': str(total_forms),
            'entries-INITIAL_FORMS': '0',
            'entries-MIN_NUM_FORMS': '0',
            'entries-MAX_NUM_FORMS': '1000',
        }
        if entry_fields:
            data.update(entry_fields)
        if delete_flags:
            for idx, flag in delete_flags.items():
                data[f'entries-{idx}-DELETE'] = flag
        self.client.force_login(user or self.writer)
        return self.client.post(self._save_url(), data)


class BOMEmptyTableValidationTests(BOMSaveBase):
    """空表校验：空表/空白行/全删除 均被拒绝且不留空 BOM。"""

    def test_zero_forms_rejected(self):
        """0 行明细 → 拒绝，不创建 BOM，任务保持 PENDING。"""
        resp = self._post_bom(total_forms=0)
        self.assertEqual(resp.status_code, 200)  # 校验失败重渲染
        self.assertContains(resp, '色粉配比BOM不能为空')
        self.assertFalse(ColorPowderBOM.objects.filter(formula=self.formula).exists())
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, ColorMatchingTask.Status.PENDING)

    def test_blank_row_rejected(self):
        """1 行全空白明细 → 拒绝。"""
        resp = self._post_bom(total_forms=1, entry_fields=self._blank_entry_fields(0))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '色粉配比BOM不能为空')
        self.assertFalse(ColorPowderBOM.objects.filter(formula=self.formula).exists())

    def test_all_rows_deleted_rejected(self):
        """所有行均被标记删除 → 拒绝。"""
        resp = self._post_bom(total_forms=1, entry_fields=self._entry_fields(0, self.raw.pk),
                              delete_flags={0: 'on'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '色粉配比BOM不能为空')
        self.assertFalse(ColorPowderBOM.objects.filter(formula=self.formula).exists())

    def test_batch_save_empty_also_rejected(self):
        """批量保存模式下空表同样被拦截，不触发批量复制。"""
        resp = self._post_bom(total_forms=0, batch_save_mode='save')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '色粉配比BOM不能为空')
        self.assertFalse(ColorPowderBOM.objects.filter(formula=self.formula).exists())

    def test_valid_row_saves_and_completes_task(self):
        """1 行有效明细 → 保存成功，推进任务到 COMPLETED。"""
        resp = self._post_bom(total_forms=1, entry_fields=self._entry_fields(0, self.raw.pk))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(self._project_url(), resp.url)

        bom = ColorPowderBOM.objects.get(formula=self.formula)
        self.assertEqual(bom.filled_by, self.writer)
        self.assertEqual(bom.entries.count(), 1)
        entry = bom.entries.first()
        self.assertEqual(entry.raw_material_id, self.raw.pk)
        self.assertEqual(entry.percentage, Decimal('0.500'))

        # 单一配方全部填完 → complete_task → COMPLETED
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, ColorMatchingTask.Status.COMPLETED)
        self.assertEqual(self.task.operator, self.writer)


class BOMFillButtonAndRedirectTests(BOMSaveBase):
    """入口与跳转：空卡片「填写」按钮 + 列表按钮条件化与跳转参数。"""

    def _create_empty_bom(self):
        """创建一条 0 条目的 ColorPowderBOM（模拟已填写主表但无明细）。"""
        return ColorPowderBOM.objects.create(formula=self.formula, filled_by=self.writer)

    def test_empty_bom_write_permission_shows_fill_button(self):
        """0 条目 BOM + 写权限 → 空卡片显示「填写」按钮（edit=1），不显示表单。"""
        self._create_empty_bom()
        self.client.force_login(self.writer)
        resp = self.client.get(self._project_url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '尚未填写色粉配比BOM')
        self.assertContains(resp, 'edit=1')          # 「填写」按钮跳转编辑态
        self.assertNotContains(resp, 'id="bom-form"')  # 仍未进入表单态

    def test_empty_bom_no_permission_no_fill_button(self):
        """0 条目 BOM + 无写权限 → 仅提示只读，无「填写」按钮。"""
        self._create_empty_bom()
        self.client.force_login(self.viewer)
        resp = self.client.get(self._project_url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '尚未填写色粉配比BOM')
        self.assertContains(resp, '仅有查看权限')
        self.assertNotContains(resp, 'edit=1')

    def test_task_list_button_hidden_when_all_filled(self):
        """已填完 → 任务列表不再显示「填写配色」按钮。"""
        self._post_bom(total_forms=1, entry_fields=self._entry_fields(0, self.raw.pk))
        self.client.force_login(self.viewer)
        resp = self.client.get(self._list_url())
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, '填写配色')

    def test_task_list_button_shown_with_unfilled_and_redirect(self):
        """未填 → 任务列表显示按钮，且跳转参数指向首个未填配方。"""
        self.client.force_login(self.viewer)
        resp = self.client.get(self._list_url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '填写配色')
        self.assertContains(resp, 'formula_id=')       # 携带配方定位参数
        self.assertContains(resp, f'formula_id={self.formula.pk}')

    def test_project_list_button_hidden_when_all_filled(self):
        """已填完 → 项目列表不再显示「填写配色」按钮。"""
        self._post_bom(total_forms=1, entry_fields=self._entry_fields(0, self.raw.pk))
        self.client.force_login(self.viewer)
        resp = self.client.get(self._project_list_url())
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, '填写配色')

    def test_project_list_button_shown_with_unfilled_and_redirect(self):
        """未填 → 项目列表显示按钮，跳转参数指向首个未填配方。"""
        self.client.force_login(self.viewer)
        resp = self.client.get(self._project_list_url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '填写配色')
        self.assertContains(resp, f'formula_id={self.formula.pk}')


class ColorTaskStatusTabTests(BOMSaveBase):
    """配色任务列表卡片头部的「配色状态」tab 筛选器回归。"""

    def _create_second_order(self, status):
        """创建第二个工单 + 配色任务（指定状态），用于验证 tab 过滤。"""
        mt = MaterialType.objects.get(pk=self.formula.material_type_id)
        creator = self._make_user(f'creator_{status}', self.sales)
        formula = LabFormula.objects.create(
            code=f'BOMT-F-{status}', name='对照配方', material_type=mt,
            project=self.project, project_node=self.node, creator=creator)
        order = ProductionOrder.objects.create(
            creator=creator, code=f'BOMT-O-{status}', trial_code=formula.code,
            quantity_planned=100, status=ProductionOrder.Status.EXTRUDING,
            project=self.project)
        ProductionOrderFormulaDetail.objects.create(
            production_order=order, formula=formula,
            planned_quantity=100, needs_color_matching=True)
        ColorMatchingTask.objects.create(
            production_order=order, status=status)
        return order

    def test_tab_ui_renders_all_statuses(self):
        """列表页渲染 5 个状态 tab，默认高亮「全部状态」。"""
        self.client.force_login(self.viewer)
        resp = self.client.get(self._list_url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '全部状态')
        self.assertContains(resp, '待配色')
        self.assertContains(resp, '配色中')
        self.assertContains(resp, '已完成')
        self.assertContains(resp, '无需配色')
        # 默认 current_status=ALL → 「全部状态」tab active
        self.assertContains(resp, 'status=ALL')
        # tab 链接携带 page=1 归位
        self.assertContains(resp, 'page=1')

    def test_filter_by_status_returns_only_matching(self):
        """?status=COMPLETED 仅返回配色任务 COMPLETED 的工单。"""
        completed_order = self._create_second_order(ColorMatchingTask.Status.COMPLETED)
        # 基准任务为 PENDING
        self.client.force_login(self.viewer)

        resp = self.client.get(f"{self._list_url()}?status=COMPLETED")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, completed_order.code)
        self.assertNotContains(resp, self.order.code)  # PENDING 工单被排除

    def test_filter_all_and_invalid_defaults_to_all(self):
        """?status=ALL 或非法值 → 不施加状态过滤（返回全部）。"""
        self._create_second_order(ColorMatchingTask.Status.COMPLETED)
        self.client.force_login(self.viewer)

        for param in ('ALL', 'BOGUS'):
            resp = self.client.get(f"{self._list_url()}?status={param}")
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, self.order.code)           # PENDING
            self.assertContains(resp, f'BOMT-O-{ColorMatchingTask.Status.COMPLETED}')

    def test_current_status_context_defaults_to_all(self):
        """无 status 参数时 current_status 默认 ALL（「全部状态」高亮）。"""
        self.client.force_login(self.viewer)
        resp = self.client.get(self._list_url())
        self.assertEqual(resp.context['current_status'], 'ALL')


class BOMRedirectHelperTests(TestCase):
    """跳转参数工具函数单元回归。"""

    def test_fill_redirect_params_empty_for_none(self):
        self.assertEqual(_fill_redirect_params(None), '')

    def test_first_unfilled_skips_formula_without_node(self):
        """无 project_node 的未填配方应被跳过，返回带节点的首个未填配方。"""
        mt = MaterialType.objects.create(name='MT')
        material = MaterialLibrary.objects.create(grade_name='G', category=mt)
        mgr_user = User.objects.create_user(username='mgr2', email='m2@t.dev', password='x')
        project = Project.objects.create(
            code='PRJ', name='PRJ', manager=mgr_user, material=material)
        node = ProjectNode.objects.create(
            project=project, stage='RND', round=1, order=0, status='DOING')
        creator = User.objects.create_user(username='cr2', email='c2@t.dev', password='x')

        # 无 project_node
        no_node = LabFormula.objects.create(
            code='F-NO-NODE', name='无节点', material_type=mt,
            project=project, creator=creator)
        # 有 project_node
        with_node = LabFormula.objects.create(
            code='F-WITH-NODE', name='有节点', material_type=mt,
            project=project, project_node=node, creator=creator)

        order = ProductionOrder.objects.create(
            creator=creator, code='O-REDIR', trial_code='F-WITH-NODE',
            quantity_planned=100, status=ProductionOrder.Status.EXTRUDING,
            project=project)
        ProductionOrderFormulaDetail.objects.create(
            production_order=order, formula=no_node, needs_color_matching=True)
        ProductionOrderFormulaDetail.objects.create(
            production_order=order, formula=with_node, needs_color_matching=True)
        ColorMatchingTask.objects.create(
            production_order=order, status=ColorMatchingTask.Status.PENDING)

        found = _first_unfilled_formula(order.formula_details)
        self.assertEqual(found.pk, with_node.pk)

        params = _fill_redirect_params(found)
        self.assertEqual(
            params, f'stage={node.stage}&round={node.round}&formula_id={with_node.pk}')