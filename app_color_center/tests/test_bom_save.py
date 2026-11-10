"""色粉配比 BOM 保存回归测试。

覆盖本轮两项改动：

1. 空表校验：保存「配色 BOM」时，若明细表格全部为空（0 行、全空白行、或全部被
   标记删除），formset 拒绝提交，不落库空 BOM，也不推进 ColorMatchingTask。
2. 入口与跳转：
   - fill.html 的「尚未填写色粉配比BOM」卡片在有写权限时补「填写」按钮（?edit=1）；
   - 任务/项目列表的「填写配色」按钮仅在存在未填 BOM 时显示，且跳转参数指向首个
     未填配方（stage/round/formula_id 完整）。
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app_user.models import Department, ModuleAccessConfig, RoleGroup, UserRole
from app_user.services.identity_service import IdentityService

from app_color_center.forms import ColorPowderBOMEntryForm
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
            f'entries-{idx}-percentage': '125',
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

        edit = self.client.get(self._project_url(), {
            'stage': 'RND', 'round': '1',
            'formula_id': self.formula.pk, 'edit': '1',
        })
        self.assertContains(edit, 'value="125')

    def test_one_gram_stores_as_four_thousandths(self):
        """1 克 = 0.004 份。"""
        fields = self._entry_fields(0, self.raw.pk)
        fields['entries-0-percentage'] = '1'
        resp = self._post_bom(total_forms=1, entry_fields=fields)
        self.assertEqual(resp.status_code, 302)
        entry = ColorPowderBOM.objects.get(formula=self.formula).entries.get()
        self.assertEqual(entry.percentage, Decimal('0.004'))

    def test_sub_gram_keeps_six_decimal_places(self):
        """0.001 克以前会被 3 位小数收成 0，现在存成 0.000004。"""
        fields = self._entry_fields(0, self.raw.pk)
        fields['entries-0-percentage'] = '0.001'
        resp = self._post_bom(total_forms=1, entry_fields=fields)
        self.assertEqual(resp.status_code, 302)
        entry = ColorPowderBOM.objects.get(formula=self.formula).entries.get()
        self.assertEqual(entry.percentage, Decimal('0.000004'))

    def test_three_decimal_grams_round_trip(self):
        """3 位小数的克数入库后再打开，输入框和只读卡片都还是原值。"""
        fields = self._entry_fields(0, self.raw.pk)
        fields['entries-0-percentage'] = '1.234'
        resp = self._post_bom(total_forms=1, entry_fields=fields)
        self.assertEqual(resp.status_code, 302)
        entry = ColorPowderBOM.objects.get(formula=self.formula).entries.get()
        self.assertEqual(entry.percentage, Decimal('0.004936'))

        self.client.force_login(self.writer)
        edit = self.client.get(self._project_url(), {
            'stage': 'RND', 'round': '1',
            'formula_id': self.formula.pk, 'edit': '1',
        })
        self.assertContains(edit, 'value="1.234"')

        readonly = self.client.get(self._project_url(), {
            'stage': 'RND', 'round': '1',
            'formula_id': self.formula.pk,
        })
        self.assertContains(readonly, '1.234')

    def test_four_decimal_grams_rejected(self):
        """超过 3 位小数的克数不入库。"""
        fields = self._entry_fields(0, self.raw.pk)
        fields['entries-0-percentage'] = '1.2345'
        resp = self._post_bom(total_forms=1, entry_fields=fields)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ColorPowderBOM.objects.filter(formula=self.formula).exists())

    def test_raw_material_choices_stay_on_the_selected_row(self):
        """下拉只带当前行的原材料，不能把整张原材料表渲染进每个 select。"""
        other = RawMaterial.objects.create(
            name='不应出现的原料', model_name='NO-SHOW', category=self.raw.category)
        self._post_bom(total_forms=1, entry_fields=self._entry_fields(0, self.raw.pk))
        entry = ColorPowderBOM.objects.get(formula=self.formula).entries.get()

        form = ColorPowderBOMEntryForm(instance=entry)
        self.assertEqual(
            list(form.fields['raw_material'].queryset.values_list('pk', flat=True)),
            [self.raw.pk],
        )
        empty = ColorPowderBOMEntryForm()
        self.assertEqual(list(empty.fields['raw_material'].queryset), [])

        self.client.force_login(self.writer)
        edit = self.client.get(self._project_url(), {
            'stage': 'RND', 'round': '1',
            'formula_id': self.formula.pk, 'edit': '1',
        })
        self.assertContains(edit, self.raw.name)
        self.assertNotContains(edit, other.name)


class BOMFillButtonAndRedirectTests(BOMSaveBase):
    """入口与跳转：未完成任务直接进编辑，列表按钮按是否已确认显示。"""

    def _create_empty_bom(self):
        """创建一条 0 条目的 ColorPowderBOM（模拟已填写主表但无明细）。"""
        return ColorPowderBOM.objects.create(formula=self.formula, filled_by=self.writer)

    def test_empty_bom_write_permission_opens_the_form(self):
        """0 条目 BOM + 写权限 + 任务未完成 → 直接进编辑，不再停在「填写」按钮。"""
        self._create_empty_bom()
        self.client.force_login(self.writer)
        resp = self.client.get(self._project_url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="bom-form"')
        self.assertNotContains(resp, '>已填写<')

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

    def test_project_list_button_shows_detail_when_all_filled(self):
        """已填完 → 项目列表显示「查看详情」按钮，不带配方定位参数。"""
        self._post_bom(total_forms=1, entry_fields=self._entry_fields(0, self.raw.pk))
        self.client.force_login(self.viewer)
        resp = self.client.get(self._project_list_url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '查看详情')
        self.assertNotContains(resp, 'formula_id=')

    def test_project_list_button_shows_detail_when_unfilled(self):
        """未填 → 项目列表显示「查看详情」按钮，不带配方定位参数。"""
        self.client.force_login(self.viewer)
        resp = self.client.get(self._project_list_url())
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, '填写配色')
        self.assertContains(resp, '查看详情')
        self.assertNotContains(resp, 'formula_id=')

    def test_project_list_progress_counts_only_color_order_lines(self):
        """项目只要挂了配方就列出。进度分母只数工单里勾了需要配色的明细。"""
        bare = Project.objects.create(
            code='BOMT-P-BARE', name='无配方项目', manager=self.project.manager,
            material=self.material)
        self.client.force_login(self.viewer)
        listed = self.client.get(self._project_list_url())
        self.assertContains(listed, self.project.name)
        self.assertContains(listed, '0/1')
        self.assertNotContains(listed, bare.name)

        self.order.delete()
        without_order = self.client.get(self._project_list_url())
        self.assertContains(without_order, self.project.name)
        self.assertContains(without_order, '0/0')

        self.order = ProductionOrder.objects.create(
            creator=self.formula.creator, code='BOMT-O-001', trial_code=self.formula.code,
            quantity_planned=100, status=ProductionOrder.Status.DRAFT,
            project=self.project)
        detail = ProductionOrderFormulaDetail.objects.create(
            production_order=self.order, formula=self.formula,
            planned_quantity=100, needs_color_matching=False)
        unmarked = self.client.get(self._project_list_url())
        self.assertContains(unmarked, '0/0')

        detail.needs_color_matching = True
        detail.save(update_fields=['needs_color_matching'])
        marked = self.client.get(self._project_list_url())
        self.assertContains(marked, '0/1')

    def test_project_list_filters_name_and_product_separately(self):
        """项目名称、成品编号/成品牌号分开筛，互不串到另一个框。"""
        self.client.force_login(self.viewer)
        page = self.client.get(self._project_list_url())
        self.assertContains(page, 'placeholder="项目名称"')
        self.assertContains(page, 'placeholder="成品编号/成品牌号"')

        by_name = self.client.get(self._project_list_url(), {'name': 'BOM回归'})
        self.assertContains(by_name, self.project.name)
        by_material_in_name = self.client.get(
            self._project_list_url(), {'name': self.material.grade_name})
        self.assertNotContains(by_material_in_name, self.project.name)

        by_code = self.client.get(
            self._project_list_url(), {'product': self.material.sap_material_code})
        self.assertContains(by_code, self.project.name)
        by_grade = self.client.get(
            self._project_list_url(), {'product': self.material.grade_name})
        self.assertContains(by_grade, self.project.name)
        by_name_in_product = self.client.get(
            self._project_list_url(), {'product': 'BOM回归'})
        self.assertNotContains(by_name_in_product, self.project.name)


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


class ColorBomWithoutTaskTests(BOMSaveBase):
    """没下发配色任务也能补色粉。下发前填过的，要配色员再保存一次才算完成。"""

    def _fill_bom_before_the_task(self):
        """任务已经在，但色粉是更早填的。update 绕开 auto_now。"""
        bom = ColorPowderBOM.objects.create(formula=self.formula, filled_by=self.writer)
        ColorPowderBOMEntry.objects.create(
            color_powder_bom=bom,
            raw_material=self.raw,
            percentage=Decimal('0.500'),
            feeding_port='1_MAIN',
            weighing_scale='D',
        )
        ColorPowderBOM.objects.filter(pk=bom.pk).update(
            updated_at=timezone.now() - timedelta(days=1))
        return bom

    def _formula_url(self):
        return (
            f'{self._project_url()}?stage={self.node.stage}'
            f'&round={self.node.round}&formula_id={self.formula.pk}'
        )

    def test_can_save_color_bom_before_a_task_exists(self):
        """需要配色、但任务还没建：能填、能存，保存不会凭空建任务。"""
        self.task.delete()
        self.client.force_login(self.writer)
        page = self.client.get(self._project_url())
        self.assertContains(page, 'id="bom-form"')

        resp = self._post_bom(
            total_forms=1, entry_fields=self._entry_fields(0, self.raw.pk))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ColorPowderBOM.objects.filter(formula=self.formula).exists())
        self.assertFalse(
            ColorMatchingTask.objects.filter(production_order=self.order).exists())

    def test_can_save_color_bom_with_no_order(self):
        """实验单没有关联任何工单：能看到表单，能保存，不新建工单或配色任务。"""
        self.order.delete()
        self.client.force_login(self.writer)
        page = self.client.get(self._formula_url())
        self.assertContains(page, 'id="bom-form"')
        self.assertNotContains(page, '该配方无需配色')

        order_count = ProductionOrder.objects.count()
        task_count = ColorMatchingTask.objects.count()
        resp = self._post_bom(
            total_forms=1, entry_fields=self._entry_fields(0, self.raw.pk))
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn(reverse('permission_denied'), resp.url)
        self.assertTrue(ColorPowderBOM.objects.filter(formula=self.formula).exists())
        self.assertEqual(ProductionOrder.objects.count(), order_count)
        self.assertEqual(ColorMatchingTask.objects.count(), task_count)

    def test_can_save_when_order_does_not_need_color(self):
        """有工单但没勾需要配色，同样能保存，也不把配色任务判成完成。"""
        detail = self.order.formula_details.get()
        detail.needs_color_matching = False
        detail.save()
        self.task.status = ColorMatchingTask.Status.NOT_REQUIRED
        self.task.save(update_fields=['status'])

        self.client.force_login(self.writer)
        page = self.client.get(self._formula_url())
        self.assertContains(page, 'id="bom-form"')

        resp = self._post_bom(
            total_forms=1, entry_fields=self._entry_fields(0, self.raw.pk))
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn(reverse('permission_denied'), resp.url)
        self.assertTrue(ColorPowderBOM.objects.filter(formula=self.formula).exists())
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, ColorMatchingTask.Status.NOT_REQUIRED)

    def test_prefilled_bom_opens_in_edit_until_the_colorist_saves(self):
        """下发前已有明细：进度不满，有写权限直接进编辑。再保存一次才完成。"""
        self._fill_bom_before_the_task()

        self.client.force_login(self.writer)
        page = self.client.get(self._formula_url())
        self.assertContains(page, 'id="bom-form"')
        self.assertNotContains(page, '>已填写<')
        self.assertContains(page, '色粉BOM待填写')

        listing = self.client.get(self._list_url())
        self.assertEqual(
            listing.context['order_stats'][self.order.pk], {'total': 1, 'done': 0})
        self.assertContains(listing, '填写配色')

        resp = self._post_bom(
            total_forms=1, entry_fields=self._entry_fields(0, self.raw.pk))
        self.assertEqual(resp.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, ColorMatchingTask.Status.COMPLETED)

        again = self.client.get(self._formula_url())
        self.assertNotContains(again, 'id="bom-form"')
        self.assertContains(again, '>已填写<')

    def test_viewer_sees_prefilled_rows_without_the_filled_badge(self):
        """没写权限的人看得到明细，但不标已填写，也不出表单。"""
        self._fill_bom_before_the_task()
        self.client.force_login(self.viewer)
        page = self.client.get(self._formula_url())
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, self.raw.name)
        self.assertNotContains(page, 'id="bom-form"')
        self.assertNotContains(page, '>已填写<')

    def test_saving_one_prefilled_version_leaves_the_other_open(self):
        """只确认了其中一个版本，任务停在配色中，进度按已确认的算。"""
        self._fill_bom_before_the_task()
        other = LabFormula.objects.create(
            code='BOMT-F-002', name='另一配方',
            material_type=self.formula.material_type,
            project=self.project, project_node=self.node,
            creator=self.formula.creator, version=1)
        ProductionOrderFormulaDetail.objects.create(
            production_order=self.order, formula=other,
            planned_quantity=100, needs_color_matching=True)

        resp = self._post_bom(
            total_forms=1, entry_fields=self._entry_fields(0, self.raw.pk))
        self.assertEqual(resp.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, ColorMatchingTask.Status.IN_PROGRESS)

        listing = self.client.get(self._list_url())
        self.assertEqual(
            listing.context['order_stats'][self.order.pk], {'total': 2, 'done': 1})