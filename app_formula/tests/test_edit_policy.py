"""实验单编辑分级策略（FormulaEditPolicy）与版本增删的回归测试。

覆盖三档编辑规则：
    L1 审批前（无工单 / DRAFT / CANCELED）—— 可改内容 + 可增删版本
    L2 审批中~已发单（WORKFLOW_RUNNING / ACCEPTED）—— 可改内容，版本结构冻结
    L3 投产中及之后（EXTRUDING 及以后）—— 整页只读

以及 L1 结构变更时的连带清理、版本重编号、附件清理。
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app_material.models import MaterialType
from app_formula.models import LabFormula
from app_formula.services import FormulaEditPolicy, FormulaVersionError
from app_project.models import Project, ProjectNode, ProjectStage
from app_mold_injection.models import (
    MoldRequirement, MoldRequirementFormulaDetail, MoldType)
from app_trial_production.models import ProductionOrder, ProductionOrderFormulaDetail

User = get_user_model()


def _make_user(username, superuser=True):
    if superuser:
        return User.objects.create_superuser(
            username=username, email=f'{username}@test.local', password='x')
    return User.objects.create_user(
        username=username, email=f'{username}@test.local', password='x')


def _edit_post(**overrides):
    """构造编辑页 POST 数据（不含 code —— 模板从不提交该字段）。"""
    data = {
        'next': '',
        'num_columns': '1',
        'name': '配方A',
        'material_type': '',
        'process': '',
        'project': '',
        'project_node': '',
        'description': '',
        'material_color_name': '',
        'pantone_code': '',
        'rgb_value': '',
        'bom-TOTAL_FORMS': '0',
        'bom-INITIAL_FORMS': '0',
        'bom-MIN_NUM_FORMS': '0',
        'bom-MAX_NUM_FORMS': '1000',
        'test-TOTAL_FORMS': '0',
        'test-INITIAL_FORMS': '0',
        'test-MIN_NUM_FORMS': '0',
        'test-MAX_NUM_FORMS': '1000',
    }
    data.update(overrides)
    return data


class SingleVersionEditCodeTests(TestCase):
    """单版本实验单编辑 —— 实验单号必须保持不变。

    模板把单号渲染成裸 <input readonly>（form.html:77-81），从不提交 code；
    而 LabFormulaForm.Meta.fields 含 'code'，`code.required = False`。
    若走 form.save() 路径，cleaned_data['code'] 会是空串，
    触发 LabFormula.save() 的 `if not self.code` 分支重新生成单号。
    """

    def setUp(self):
        self.user = _make_user('editor')
        self.mt = MaterialType.objects.create(name='PA66')
        self.formula = LabFormula.objects.create(
            code='T-0001', name='原始配方', material_type=self.mt,
            creator=self.user, version=1)
        self.client.force_login(self.user)

    def test_single_version_edit_keeps_code(self):
        """编辑单版本实验单不得改变实验单号。

        历史上这条路径走的是 form.save()，而模板从不提交 code 字段，
        会把单号清空触发放 LabFormula.save() 的重生成分支 ——
        实验单被拆散、版本分组丢失。现在只有"按列写入"这一条路径。
        """
        resp = self.client.post(
            reverse('formula_edit', kwargs={'pk': self.formula.pk}),
            _edit_post(name='改名后', material_type=self.mt.pk,
                       column_formula_ids=[str(self.formula.pk)]),
        )
        self.assertEqual(resp.status_code, 302, '编辑保存应重定向')

        self.formula.refresh_from_db()
        self.assertEqual(self.formula.name, '改名后', '配方名称应已更新')
        self.assertEqual(
            self.formula.code, 'T-0001',
            '编辑配方不得改变实验单号（重新生成单号会拆散实验单的版本分组）')

    def test_single_version_page_renders_as_one_column(self):
        """单版本实验单也走批量（列）路径 —— 否则编辑页加不出新版本。"""
        resp = self.client.get(
            reverse('formula_edit', kwargs={'pk': self.formula.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content.count(b'name="column_formula_ids"'), 1)
        self.assertContains(resp, 'id="add-pct-col"', msg_prefix='应能新增版本')

    def test_post_without_column_info_is_rejected(self):
        """拿不到列标识的请求（旧页面/被裁剪）必须整体拒绝，不能只改主表单。

        若容忍这种请求，就得有一条绕过"按列写入"的落库路径 ——
        那正是上面那个单号重生成缺陷的来源。
        """
        resp = self.client.post(
            reverse('formula_edit', kwargs={'pk': self.formula.pk}),
            _edit_post(name='改名后', material_type=self.mt.pk),
        )
        self.assertEqual(resp.status_code, 200, '被拒后重渲染表单页')
        self.formula.refresh_from_db()
        self.assertEqual(self.formula.name, '原始配方', '被拒时不得写入任何改动')


class FormulaEditPolicyTests(TestCase):
    """分级规则 —— 依据关联工单中最靠后的状态。"""

    def setUp(self):
        self.user = _make_user('planner')
        self.mt = MaterialType.objects.create(name='PA66')
        self.formulas = [
            LabFormula.objects.create(
                code='T-1000', name=f'配方v{i}', material_type=self.mt,
                creator=self.user, version=i)
            for i in (1, 2)
        ]

    def _make_order(self, status, code='TP-1000'):
        order = ProductionOrder.objects.create(
            code=code, trial_code='T-1000', status=status, creator=self.user)
        for f in self.formulas:
            ProductionOrderFormulaDetail.objects.create(
                production_order=order, formula=f, planned_quantity=10)
        return order

    def test_no_order_is_l1(self):
        policy = FormulaEditPolicy.resolve(self.formulas)
        self.assertEqual(policy['tier'], FormulaEditPolicy.TIER_L1)
        self.assertTrue(policy['can_edit_content'])
        self.assertTrue(policy['can_manage_versions'])
        self.assertEqual(policy['removable_order_codes'], [])
        self.assertEqual(policy['blocking_order_codes'], [])

    def test_draft_is_l1_and_removable(self):
        self._make_order(ProductionOrder.Status.DRAFT, code='TP-DRAFT')
        policy = FormulaEditPolicy.resolve(self.formulas)
        self.assertEqual(policy['tier'], FormulaEditPolicy.TIER_L1)
        self.assertTrue(policy['can_manage_versions'])
        self.assertEqual(policy['removable_order_codes'], ['TP-DRAFT'])

    def test_canceled_is_l1_and_removable(self):
        """取消的工单视为「审批前」，且会被连带删除。"""
        self._make_order(ProductionOrder.Status.CANCELED, code='TP-CANCELED')
        policy = FormulaEditPolicy.resolve(self.formulas)
        self.assertEqual(policy['tier'], FormulaEditPolicy.TIER_L1)
        self.assertTrue(policy['can_manage_versions'])
        self.assertEqual(policy['removable_order_codes'], ['TP-CANCELED'])

    def test_approving_and_accepted_are_l2(self):
        for status in (ProductionOrder.Status.WORKFLOW_RUNNING, ProductionOrder.Status.ACCEPTED):
            with self.subTest(status=status):
                ProductionOrder.objects.all().delete()
                self._make_order(status, code=f'TP-{status}')
                policy = FormulaEditPolicy.resolve(self.formulas)
                self.assertEqual(policy['tier'], FormulaEditPolicy.TIER_L2)
                self.assertTrue(policy['can_edit_content'], 'L2 仍可改 BOM')
                self.assertFalse(policy['can_manage_versions'], 'L2 版本结构冻结')
                self.assertEqual(policy['blocking_order_codes'], [f'TP-{status}'])

    def test_producing_and_later_are_l3(self):
        for status in (ProductionOrder.Status.EXTRUDING, ProductionOrder.Status.INJECTION_MOLDING,
                       ProductionOrder.Status.TESTING, ProductionOrder.Status.COMPLETED):
            with self.subTest(status=status):
                ProductionOrder.objects.all().delete()
                self._make_order(status, code=f'TP-{status}')
                policy = FormulaEditPolicy.resolve(self.formulas)
                self.assertEqual(policy['tier'], FormulaEditPolicy.TIER_L3)
                self.assertFalse(policy['can_edit_content'], 'L3 整页只读')
                self.assertFalse(policy['can_manage_versions'])

    def test_mixed_takes_the_most_advanced(self):
        self._make_order(ProductionOrder.Status.DRAFT, code='TP-A')
        self._make_order(ProductionOrder.Status.ACCEPTED, code='TP-B')
        policy = FormulaEditPolicy.resolve(self.formulas)
        self.assertEqual(policy['tier'], FormulaEditPolicy.TIER_L2, '混合状态取最靠后的')
        self.assertFalse(policy['can_manage_versions'])
        self.assertEqual(policy['removable_order_codes'], [], '非 L1 不谈连带删除')
        self.assertEqual(policy['blocking_order_codes'], ['TP-B'])

    def test_draft_plus_completed_is_l3(self):
        self._make_order(ProductionOrder.Status.DRAFT, code='TP-A')
        self._make_order(ProductionOrder.Status.COMPLETED, code='TP-B')
        policy = FormulaEditPolicy.resolve(self.formulas)
        self.assertEqual(policy['tier'], FormulaEditPolicy.TIER_L3)

    def test_no_formulas_is_l1(self):
        policy = FormulaEditPolicy.resolve([])
        self.assertEqual(policy['tier'], FormulaEditPolicy.TIER_L1)
        self.assertTrue(policy['can_manage_versions'])


class EditTierEnforcementTests(TestCase):
    """编辑页在 L2/L3 的服务端拦截 —— 不能只靠前端隐藏按钮。"""

    def setUp(self):
        self.user = _make_user('editor2')
        self.mt = MaterialType.objects.create(name='PA66')
        self.formula = LabFormula.objects.create(
            code='T-2000', name='原始配方', material_type=self.mt,
            creator=self.user, version=1)
        self.client.force_login(self.user)

    def _make_order(self, status, formulas=None):
        formulas = formulas or [self.formula]
        order = ProductionOrder.objects.create(
            code=f'TP-{status}', trial_code='T-2000', status=status, creator=self.user)
        for f in formulas:
            ProductionOrderFormulaDetail.objects.create(
                production_order=order, formula=f, planned_quantity=10)
        return order

    def _edit_url(self, formula=None):
        return reverse('formula_edit', kwargs={'pk': (formula or self.formula).pk})

    # ── L3：整页只读 ──

    def test_l3_edit_page_is_readonly(self):
        self._make_order(ProductionOrder.Status.EXTRUDING)
        resp = self.client.get(self._edit_url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '已整体锁定', msg_prefix='L3 应显示锁定横幅')
        self.assertNotContains(resp, '保存配方', msg_prefix='L3 不应渲染保存按钮')
        self.assertContains(resp, 'disabled', msg_prefix='L3 表单控件应 disabled')

    def test_l3_post_is_rejected_and_changes_nothing(self):
        self._make_order(ProductionOrder.Status.COMPLETED)
        resp = self.client.post(
            self._edit_url(),
            _edit_post(name='偷偷改名', material_type=self.mt.pk),
        )
        self.assertEqual(resp.status_code, 302, 'L3 应拒绝写入并重定向回只读页')
        self.formula.refresh_from_db()
        self.assertEqual(self.formula.name, '原始配方', 'L3 下配方不得被修改')

    # ── L2：可改内容，版本结构冻结 ──

    def test_l2_edit_page_banner(self):
        self._make_order(ProductionOrder.Status.ACCEPTED)
        resp = self.client.get(self._edit_url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '版本结构已冻结')

    def test_l2_allows_content_edit(self):
        self._make_order(ProductionOrder.Status.WORKFLOW_RUNNING)
        self.client.post(
            self._edit_url(),
            _edit_post(name='审批中改名', material_type=self.mt.pk,
                       column_formula_ids=[str(self.formula.pk)]),
        )
        self.formula.refresh_from_db()
        self.assertEqual(self.formula.name, '审批中改名', 'L2 仍可改基础信息')

    def test_l2_rejects_forged_version_removal(self):
        """伪造 POST 丢掉一个版本 → 必须被拒，而不是静默删版本。"""
        v2 = LabFormula.objects.create(
            code='T-2000', name='配方v2', material_type=self.mt,
            creator=self.user, version=2)
        self._make_order(ProductionOrder.Status.ACCEPTED, formulas=[self.formula, v2])

        resp = self.client.post(
            self._edit_url(),
            _edit_post(name='伪造', material_type=self.mt.pk, formula_ids=[self.formula.pk]),
        )
        self.assertEqual(resp.status_code, 200, '被拒后应重渲染表单页')
        self.assertEqual(
            LabFormula.objects.filter(code='T-2000').count(), 2,
            'L2 下伪造 POST 不得删除版本')


class VersionEditViewTests(TestCase):
    """L1 编辑页通过列提交增删配方版本。"""

    def setUp(self):
        self.user = _make_user('vereditor')
        self.mt = MaterialType.objects.create(name='PA66')
        self.code = 'T-4000'
        self.v1, self.v2, self.v3 = [
            LabFormula.objects.create(
                code=self.code, name=f'配方v{i}', material_type=self.mt,
                creator=self.user, version=i)
            for i in (1, 2, 3)
        ]
        self.client.force_login(self.user)

    def _post(self, column_ids, **overrides):
        data = _edit_post(material_type=self.mt.pk, **overrides)
        data.setdefault('name', '配方A')
        data['column_formula_ids'] = column_ids
        return self.client.post(
            reverse('formula_edit', kwargs={'pk': self.v1.pk}), data)

    def _versions(self):
        return list(LabFormula.objects.filter(code=self.code)
                    .order_by('version').values_list('version', flat=True))

    def _pks(self):
        return set(LabFormula.objects.filter(code=self.code)
                   .values_list('pk', flat=True))

    def test_adds_new_version_and_renumbers(self):
        resp = self._post([str(self.v1.pk), str(self.v2.pk), str(self.v3.pk), ''])
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self._versions(), [1, 2, 3, 4])
        self.assertTrue(self._pks().issuperset({self.v1.pk, self.v2.pk, self.v3.pk}),
                        '已有版本必须保留，不能被重建')

    def test_removes_middle_version_and_compacts(self):
        resp = self._post([str(self.v1.pk), str(self.v3.pk)])
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self._versions(), [1, 2])
        self.assertFalse(LabFormula.objects.filter(pk=self.v2.pk).exists())
        self.v3.refresh_from_db()
        self.assertEqual(self.v3.version, 2, 'v3 应被压缩到 2')

    def test_inserting_column_in_middle_bumps_versions(self):
        """在 v1 与 v2 之间插一个新版本：v2 应后移到 3。"""
        resp = self._post([str(self.v1.pk), '', str(self.v2.pk)])
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self._versions(), [1, 2, 3])  # v1 / 新 / (v2→3)
        self.v2.refresh_from_db()
        self.assertEqual(self.v2.version, 3)

    def test_removing_version_drops_draft_order(self):
        order = ProductionOrder.objects.create(
            code='TP-4100', trial_code=self.code, status=ProductionOrder.Status.DRAFT,
            creator=self.user)
        ProductionOrderFormulaDetail.objects.create(
            production_order=order, formula=self.v2, planned_quantity=10)

        resp = self._post([str(self.v1.pk), str(self.v3.pk)])
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ProductionOrder.objects.filter(pk=order.pk).exists(),
                         '结构变更应连带删除草稿工单')

    def test_untouched_structure_keeps_draft_order(self):
        """只改内容不改结构时，草稿工单不受影响。"""
        order = ProductionOrder.objects.create(
            code='TP-4200', trial_code=self.code, status=ProductionOrder.Status.DRAFT,
            creator=self.user)
        ProductionOrderFormulaDetail.objects.create(
            production_order=order, formula=self.v2, planned_quantity=10)

        resp = self._post([str(self.v1.pk), str(self.v2.pk), str(self.v3.pk)])
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ProductionOrder.objects.filter(pk=order.pk).exists())

    def test_validation_error_keeps_unsaved_column(self):
        """校验失败重渲染后，用户尚未保存的新列必须还在。"""
        resp = self._post([str(self.v1.pk), str(self.v2.pk), str(self.v3.pk), ''],
                          name='')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.content.count(b'name="column_formula_ids"'), 4,
            '重渲染后应保留 4 列（含未保存的新列）')

    def test_rejects_duplicate_version_in_two_columns(self):
        resp = self._post([str(self.v1.pk), str(self.v1.pk)])
        self.assertEqual(resp.status_code, 200, '被拒后重渲染而非报错')
        self.assertEqual(self._versions(), [1, 2, 3], '被拒时不得改动数据')

    def test_new_version_inherits_project_and_node(self):
        """新增版本必须带上实验单的项目/项目节点。

        这两个字段不在逐列赋值的共享字段里（已有版本从库里取实例、原值还在，
        新增版本是新建对象），漏掉就会变成无项目的孤儿 —— 在项目的配方过程页
        和材料详情页都看不到它。
        """
        project = Project.objects.create(name='项目X', manager=self.user)
        node = ProjectNode.objects.create(
            project=project, stage=ProjectStage.RND, round=1)
        for version in (self.v1, self.v2, self.v3):
            version.project = project
            version.project_node = node
            version.save()

        resp = self._post([str(self.v1.pk), str(self.v2.pk), str(self.v3.pk), ''])
        self.assertEqual(resp.status_code, 302)

        new_version = LabFormula.objects.filter(code=self.code, version=4).first()
        self.assertIsNotNone(new_version, '应新增一个版本')
        self.assertEqual(new_version.project_id, project.pk, '新版本必须关联项目')
        self.assertEqual(new_version.project_node_id, node.pk, '新版本必须关联项目节点')

    def test_new_version_keeps_null_project_when_experiment_has_none(self):
        """实验单本身没有关联项目时，新版本也应为空 —— 不能凭空塞一个项目。"""
        resp = self._post([str(self.v1.pk), str(self.v2.pk), str(self.v3.pk), ''])
        self.assertEqual(resp.status_code, 302)

        new_version = LabFormula.objects.filter(code=self.code, version=4).first()
        self.assertIsNone(new_version.project_id)
        self.assertIsNone(new_version.project_node_id)


class FormulaFormRenderSmokeTests(TestCase):
    """form.html 由新增/编辑两个视图共用 —— 两者都必须拿到 edit_policy。

    模板里用 `{% if edit_policy.can_edit_content %}` 决定保存按钮等元素的显隐，
    任一视图漏传该上下文，页面就会整体变只读（或直接 500）。
    """

    def setUp(self):
        self.user = _make_user('smoke')
        self.mt = MaterialType.objects.create(name='PA66')
        self.formula = LabFormula.objects.create(
            code='T-7000', name='配方', material_type=self.mt,
            creator=self.user, version=1)
        self.client.force_login(self.user)

    def test_create_page_renders_editable(self):
        resp = self.client.get(reverse('formula_add'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '保存配方', msg_prefix='新建页必须可保存')

    def test_l1_edit_page_renders_editable(self):
        resp = self.client.get(
            reverse('formula_edit', kwargs={'pk': self.formula.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '保存配方')


class VersionStructureServiceTests(TestCase):
    """L1 结构变更：连带删除可删工单 + 版本重编号。"""

    def setUp(self):
        self.user = _make_user('struct')
        self.mt = MaterialType.objects.create(name='PA66')
        self.code = 'T-3000'
        self.v1, self.v2, self.v3 = [
            LabFormula.objects.create(
                code=self.code, name=f'配方v{i}', material_type=self.mt,
                creator=self.user, version=i)
            for i in (1, 2, 3)
        ]

    def _formulas(self):
        return list(LabFormula.objects.filter(code=self.code).order_by('version'))

    def _make_order(self, status, code):
        order = ProductionOrder.objects.create(
            code=code, trial_code=self.code, status=status, creator=self.user)
        ProductionOrderFormulaDetail.objects.create(
            production_order=order, formula=self.v1, planned_quantity=10)
        return order

    def test_delete_removable_orders_clears_all_references(self):
        """删工单必须连带清掉全部 PROTECT 引用，否则后续删版本会 500。"""
        order = self._make_order(ProductionOrder.Status.DRAFT, 'TP-D1')
        mold = MoldType.objects.create(
            name='样条模具', mold_code='M-001',
            mold_type=MoldType.MoldTypeChoices.TEST_SPECIMEN,
            standard=MoldType.Standard.ISO)
        requirement = MoldRequirement.objects.create(
            production_order=order, mold=mold, order=0)
        MoldRequirementFormulaDetail.objects.create(
            mold_requirement=requirement, formula=self.v1, specimen_quantity=5)

        deleted = FormulaEditPolicy.delete_removable_orders(self._formulas())

        self.assertEqual(deleted, ['TP-D1'])
        self.assertFalse(ProductionOrder.objects.filter(pk=order.pk).exists())
        self.assertFalse(ProductionOrderFormulaDetail.objects.exists())
        self.assertFalse(MoldRequirement.objects.exists())
        self.assertFalse(MoldRequirementFormulaDetail.objects.exists())
        # 引用清干净了，删配方不再被 PROTECT 挡住
        self.v1.delete()

    def test_delete_removable_orders_refuses_when_approving(self):
        self._make_order(ProductionOrder.Status.WORKFLOW_RUNNING, 'TP-R1')
        with self.assertRaises(FormulaVersionError):
            FormulaEditPolicy.delete_removable_orders(self._formulas())
        self.assertTrue(ProductionOrder.objects.filter(code='TP-R1').exists(),
                        '被拒时不得删除工单')

    def test_delete_removable_orders_noop_without_orders(self):
        self.assertEqual(FormulaEditPolicy.delete_removable_orders(self._formulas()), [])

    def test_renumber_compacts_after_removal(self):
        self.v2.delete()
        FormulaEditPolicy.renumber([self.v1, self.v3])
        self.v1.refresh_from_db()
        self.v3.refresh_from_db()
        self.assertEqual((self.v1.version, self.v3.version), (1, 2))

    def test_renumber_handles_mid_list_insertion(self):
        """列中间插入新版本：新行要落到 v2 的编号上，不先挪走就会撞唯一约束。"""
        new = LabFormula.objects.create(
            code=self.code, name='新版本', material_type=self.mt,
            creator=self.user, version=FormulaEditPolicy._RENUMBER_BASE)
        FormulaEditPolicy.renumber([self.v1, new, self.v2, self.v3])
        for f in (self.v1, new, self.v2, self.v3):
            f.refresh_from_db()
        self.assertEqual(
            (self.v1.version, new.version, self.v2.version, self.v3.version),
            (1, 2, 3, 4))
