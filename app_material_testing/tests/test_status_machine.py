"""app_material_testing 测试任务状态机语义回归测试。

覆盖本轮重构的核心契约：
1. 状态机放宽：COMPLETED 可退回 IN_PROGRESS、可到 RESULTS_WRITTEN_BACK。
2. 完整性判定 _is_complete：满/部分/空矩阵。
3. fill_results：部分→IN_PROGRESS；填满→COMPLETED；再改空→退回 IN_PROGRESS。
4. write_back_results：未完整可回写覆盖且状态不变、可反复回写；完整后回写→终态；
   终态后再次回写→幂等返回 0、不再覆盖。
5. force_complete_and_writeback：数据缺失也回写已填结果、直达终态、可推进工单。
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from common_utils.state_machine import StateMachine
from app_material.models import MaterialType, MetricCategory, TestConfig
from app_formula.models import LabFormula, FormulaTestResult
from app_project.models import Project, ProjectNode
from app_trial_production.models import ProductionOrder, ProductionOrderFormulaDetail
from app_material_testing.models import TestingTask, TrialTestResult
from app_material_testing.services import TestingTaskService

User = get_user_model()


def _make_user(username):
    return User.objects.create_user(username=username, email=f'{username}@test.local', password='x')


class TestingTaskStatusMachineTests(TestCase):
    """status machine + 完整性 + 服务层状态推进回归。"""

    def setUp(self):
        self.user = _make_user('tester')

        # 基材类型 + 测试配置项
        self.mt = MaterialType.objects.create(name='PA66')
        self.cat = MetricCategory.objects.create(name='力学', order=1)
        self.tc1 = TestConfig.objects.create(
            category=self.cat, name='拉伸强度', standard='ISO 527',
            data_type='NUMBER', unit='MPa', order=1)
        self.tc2 = TestConfig.objects.create(
            category=self.cat, name='断裂伸长率', standard='ISO 527',
            data_type='NUMBER', unit='%', order=2)

        # 项目 + 阶段节点
        mgr = _make_user('mgr')
        self.project = Project.objects.create(name='项目A', manager=mgr)
        self.node = ProjectNode.objects.create(
            project=self.project, stage='RND', round=1, order=0, status='DOING')

        # 两个配方版本
        self.f1 = LabFormula.objects.create(
            code='TRIAL-001', name='配方v1', material_type=self.mt,
            project=self.project, project_node=self.node, creator=self.user, version=1)
        self.f2 = LabFormula.objects.create(
            code='TRIAL-001', name='配方v2', material_type=self.mt,
            project=self.project, project_node=self.node, creator=self.user, version=2)

        # 工单 + 配方明细 + 测试任务
        self.order = ProductionOrder.objects.create(
            creator=self.user, code='PO-TEST-001', trial_code='TRIAL-001',
            status=ProductionOrder.Status.EXTRUDING, project=self.project)
        ProductionOrderFormulaDetail.objects.create(
            production_order=self.order, formula=self.f1, planned_quantity=100)
        ProductionOrderFormulaDetail.objects.create(
            production_order=self.order, formula=self.f2, planned_quantity=100)

        self.task = TestingTask.objects.create(
            production_order=self.order, assigned_to=self.user,
            status=TestingTask.Status.PENDING)
        self.task.test_items.set([self.tc1, self.tc2])

    # ── 状态机注册 ──

    def test_state_machine_allows_rollback_and_writeback(self):
        allowed = StateMachine.get_allowed_transitions(self.task)
        # PENDING 只到 IN_PROGRESS
        self.assertEqual(allowed, [TestingTask.Status.IN_PROGRESS])

        self.task.status = TestingTask.Status.COMPLETED
        allowed = StateMachine.get_allowed_transitions(self.task)
        self.assertIn(TestingTask.Status.IN_PROGRESS, allowed)
        self.assertIn(TestingTask.Status.RESULTS_WRITTEN_BACK, allowed)

    # ── 完整性判定 ──

    def test_is_complete_empty_matrix(self):
        """空矩阵（无填写）→ 未完整"""
        self.assertFalse(TestingTaskService._is_complete(self.task))

    def test_is_complete_partial(self):
        self._fill_cell(self.tc1, self.f1, '10.5')
        self.assertFalse(TestingTaskService._is_complete(self.task))

    def test_is_complete_full(self):
        self._fill_cell(self.tc1, self.f1, '10.5')
        self._fill_cell(self.tc2, self.f1, '3.2')
        self._fill_cell(self.tc1, self.f2, '11.0')
        self._fill_cell(self.tc2, self.f2, '3.5')
        self.assertTrue(TestingTaskService._is_complete(self.task))

    # ── fill_results 状态推进 ──

    def test_fill_partial_stays_in_progress(self):
        TestingTaskService.fill_results(self.task, [
            self._mat(self.tc1, self.f1, '10.5'),
        ], self.user)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TestingTask.Status.IN_PROGRESS)

    def test_fill_full_reaches_completed(self):
        TestingTaskService.fill_results(self.task, self._full_matrix(), self.user)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TestingTask.Status.COMPLETED)

    def test_fill_full_then_blank_rolls_back(self):
        TestingTaskService.fill_results(self.task, self._full_matrix(), self.user)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TestingTask.Status.COMPLETED)

        # 再次填写：其中一个 cell 变空 → 退回 IN_PROGRESS
        TestingTaskService.fill_results(self.task, [
            self._mat(self.tc1, self.f1, ''),   # 清空该 cell
            self._mat(self.tc2, self.f1, '3.2'),
            self._mat(self.tc1, self.f2, '11.0'),
            self._mat(self.tc2, self.f2, '3.5'),
        ], self.user)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TestingTask.Status.IN_PROGRESS)

    # ── write_back_results 覆盖 + 网关 ──

    def test_writeback_incomplete_overwrites_but_does_not_advance(self):
        TestingTaskService.fill_results(self.task, [
            self._mat(self.tc1, self.f1, '10.5'),
        ], self.user)

        written = TestingTaskService.write_back_results(self.task)
        self.assertEqual(written, 1)
        self.task.refresh_from_db()
        # 未完整 → 状态保持不变（仍 IN_PROGRESS）
        self.assertEqual(self.task.status, TestingTask.Status.IN_PROGRESS)
        # 已有结果被写入配方库
        self.assertEqual(
            FormulaTestResult.objects.get(formula=self.f1, test_config=self.tc1).value,
            Decimal('10.500'))

    def test_writeback_incomplete_can_repeat_and_overwrite(self):
        TestingTaskService.fill_results(self.task, [
            self._mat(self.tc1, self.f1, '10.5'),
        ], self.user)

        TestingTaskService.write_back_results(self.task)
        # 修改值后再次回写 → 覆盖
        TestingTaskService.fill_results(self.task, [
            self._mat(self.tc1, self.f1, '20.0'),
        ], self.user)
        TestingTaskService.write_back_results(self.task)

        self.assertEqual(
            FormulaTestResult.objects.get(formula=self.f1, test_config=self.tc1).value,
            Decimal('20.000'))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TestingTask.Status.IN_PROGRESS)

    def test_writeback_complete_reaches_terminal(self):
        TestingTaskService.fill_results(self.task, self._full_matrix(), self.user)
        written = TestingTaskService.write_back_results(self.task)
        self.assertEqual(written, 4)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TestingTask.Status.RESULTS_WRITTEN_BACK)

    def test_writeback_after_terminal_is_noop(self):
        TestingTaskService.fill_results(self.task, self._full_matrix(), self.user)
        TestingTaskService.write_back_results(self.task)

        written = TestingTaskService.write_back_results(self.task)
        self.assertEqual(written, 0)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TestingTask.Status.RESULTS_WRITTEN_BACK)

    # ── force_complete_and_writeback ──

    def test_force_complete_incomplete_reaches_terminal(self):
        TestingTaskService.fill_results(self.task, [
            self._mat(self.tc1, self.f1, '10.5'),
        ], self.user)

        written = TestingTaskService.force_complete_and_writeback(self.task)
        self.assertEqual(written, 1)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TestingTask.Status.RESULTS_WRITTEN_BACK)
        # 已填结果被覆盖回写
        self.assertEqual(
            FormulaTestResult.objects.get(formula=self.f1, test_config=self.tc1).value,
            Decimal('10.500'))

    def test_force_complete_from_pending(self):
        """完全未填也允许手动过掉 → 直达终态，written=0。"""
        written = TestingTaskService.force_complete_and_writeback(self.task)
        self.assertEqual(written, 0)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TestingTask.Status.RESULTS_WRITTEN_BACK)

    # ── 辅助 ──

    def _fill_cell(self, tc, formula, value):
        result, _ = TrialTestResult.objects.get_or_create(
            testing_task=self.task, test_config=tc, formula=formula)
        result.value = value if value else None
        result.save()

    def _mat(self, tc, formula, value):
        return {
            'test_config_id': tc.pk,
            'formula_id': formula.pk,
            'value': value or None,
            'value_text': '',
            'test_date': None,
            'remark': '',
        }

    def _full_matrix(self):
        return [
            self._mat(self.tc1, self.f1, '10.5'),
            self._mat(self.tc2, self.f1, '3.2'),
            self._mat(self.tc1, self.f2, '11.0'),
            self._mat(self.tc2, self.f2, '3.5'),
        ]


class ForceCompleteViewTests(TestCase):
    """手动完成并回写 视图端到端（超管绕过 RBAC，验证端点与跳转）。"""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.local', password='x')
        creator = _make_user('creator')
        self.mt = MaterialType.objects.create(name='PA66')
        self.cat = MetricCategory.objects.create(name='力学', order=1)
        self.tc = TestConfig.objects.create(
            category=self.cat, name='拉伸强度', standard='ISO 527',
            data_type='NUMBER', unit='MPa', order=1)

        mgr = _make_user('mgr')
        self.project = Project.objects.create(name='项目A', manager=mgr)
        self.node = ProjectNode.objects.create(
            project=self.project, stage='RND', round=1, order=0, status='DOING')
        self.formula = LabFormula.objects.create(
            code='TRIAL-002', name='配方', material_type=self.mt,
            project=self.project, project_node=self.node, creator=creator, version=1)
        self.order = ProductionOrder.objects.create(
            creator=creator, code='PO-TEST-002', trial_code='TRIAL-002',
            status=ProductionOrder.Status.EXTRUDING, project=self.project)
        ProductionOrderFormulaDetail.objects.create(
            production_order=self.order, formula=self.formula, planned_quantity=100)
        self.task = TestingTask.objects.create(
            production_order=self.order, assigned_to=creator,
            status=TestingTask.Status.PENDING)
        self.task.test_items.set([self.tc])

    def test_force_complete_endpoint_redirects_and_completes(self):
        self.client.force_login(self.admin)
        url = reverse('material_testing:force_complete', args=[self.task.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TestingTask.Status.RESULTS_WRITTEN_BACK)

    def test_force_complete_url_resolves(self):
        self.assertEqual(
            reverse('material_testing:force_complete', args=[1]),
            '/material-testing/1/force-complete/',
        )