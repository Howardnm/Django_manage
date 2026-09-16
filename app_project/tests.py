"""app_project 通知接线测试：ProjectNode 更新 → 项目负责人与成员收到通知。"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from app_notification.models import Notification
from app_project.forms import ProjectNodeUpdateForm
from app_project.models import Project, ProjectNode, ProjectStage

# 确保类型已注册 + post_save 已绑定（ready() 已导入，此处显式作保障）
import app_project.notifications  # noqa: F401

User = get_user_model()


def _make_user(username):
    return User.objects.create_user(username=username, email=f'{username}@test.local', password='x')


def _complete_progress_nodes(project):
    for node in project.nodes.exclude(stage__in=ProjectStage.non_progress_codes()):
        node.status = 'DONE'
        node.save()
    return Project.objects.get(pk=project.pk)


class ProjectNodeNotificationsTests(TestCase):
    def test_node_update_notifies_manager_and_members(self):
        manager = _make_user('manager')
        member = _make_user('member')
        outsider = _make_user('outsider')
        project = Project.objects.create(name='项目A', manager=manager)
        project.members.create(user=member)
        node = ProjectNode.objects.create(project=project, stage='INIT')

        # 首次创建不通知
        self.assertEqual(Notification.objects.filter(type='project.node_updated').count(), 0)

        # 更新节点触发通知（manager + member，排除 outsider）
        node.remark = '更新备注'
        node.save()
        recipients = set(Notification.objects.filter(
            type='project.node_updated').values_list('recipient_id', flat=True))
        self.assertEqual(recipients, {manager.pk, member.pk})
        self.assertNotIn(outsider.pk, recipients)


class ProjectStagePipelineTests(TestCase):
    def test_new_project_creates_pipeline_nodes(self):
        manager = _make_user('stage_mgr')
        project = Project.objects.create(name='阶段项目', manager=manager)
        stages = list(project.nodes.order_by('order').values_list('stage', flat=True))
        self.assertEqual(stages, [
            ProjectStage.INIT, ProjectStage.RND, ProjectStage.PILOT,
            ProjectStage.MID_TEST, ProjectStage.MASS_PROD, ProjectStage.ORDER,
            ProjectStage.MASS_TRACK,
        ])
        self.assertNotIn(ProjectStage.FEEDBACK, stages)
        self.assertNotIn('COLLECT', stages)
        self.assertNotIn('FEASIBILITY', stages)
        self.assertNotIn('PRICING', stages)
        self.assertEqual(project.current_stage, ProjectStage.INIT)
        self.assertEqual(project.progress_percent, 0)

    def test_progress_nodes_done_reaches_100_with_track_active(self):
        manager = _make_user('done_mgr')
        project = Project.objects.create(name='完成项目', manager=manager)
        project = _complete_progress_nodes(project)

        self.assertEqual(project.progress_percent, 100)
        self.assertTrue(project.is_completed)
        track = project.nodes.get(stage=ProjectStage.MASS_TRACK)
        self.assertEqual(track.status, 'DOING')
        self.assertEqual(project.current_active_node.pk, track.pk)
        self.assertEqual(project.current_stage, ProjectStage.MASS_TRACK)

        self.assertTrue(track.can_update_status)
        self.assertTrue(track.can_report_failure)
        self.assertTrue(track.can_add_feedback)
        self.assertTrue(track.can_add_formula)
        self.assertTrue(track.can_manage_content)
        self.assertTrue(track.can_be_mature)
        self.assertEqual(track.formula_button_label, '新增成熟配方')

    def test_mass_track_rejects_done_status(self):
        manager = _make_user('form_mgr')
        project = Project.objects.create(name='表单项目', manager=manager)
        project = _complete_progress_nodes(project)
        track = project.nodes.get(stage=ProjectStage.MASS_TRACK)

        form = ProjectNodeUpdateForm({'status': 'DONE', 'remark': '完成'}, instance=track)
        self.assertFalse(form.is_valid())
        self.assertIn('status', form.errors)

        form = ProjectNodeUpdateForm({'status': 'PAUSED', 'remark': '暂停跟进'}, instance=track)
        self.assertTrue(form.is_valid())

    def test_mass_track_failure_starts_next_round(self):
        manager = _make_user('fail_mgr')
        project = Project.objects.create(name='异常项目', manager=manager)
        project = _complete_progress_nodes(project)
        track = project.nodes.get(stage=ProjectStage.MASS_TRACK)

        track.perform_failure_logic('量产过程异常')
        project = Project.objects.get(pk=project.pk)

        failed = project.nodes.filter(stage=ProjectStage.MASS_TRACK, status='FAILED')
        active = project.nodes.filter(stage=ProjectStage.MASS_TRACK).exclude(status='FAILED')
        self.assertEqual(failed.count(), 1)
        self.assertEqual(active.count(), 1)
        self.assertEqual(active.get().round, 2)
        self.assertEqual(project.progress_percent, 100)
        self.assertEqual(project.current_active_node.pk, active.get().pk)

    def test_mass_track_feedback_inserts_after_current(self):
        manager = _make_user('fb_mgr')
        project = Project.objects.create(name='意见项目', manager=manager)
        project = _complete_progress_nodes(project)
        track = project.nodes.get(stage=ProjectStage.MASS_TRACK)

        project.handle_customer_feedback(track, 'CHANGE', '客户要求调整')
        project = Project.objects.get(pk=project.pk)
        track.refresh_from_db()

        feedback = project.nodes.filter(stage=ProjectStage.FEEDBACK).first()
        self.assertIsNotNone(feedback)
        self.assertGreater(feedback.order, track.order)
        self.assertEqual(project.current_active_node.pk, track.pk)
        self.assertEqual(project.progress_percent, 100)


# ── 测试数据回写页（FormulaMeanWritebackView）──
from datetime import date
from decimal import Decimal

from django.urls import reverse

from app_formula.models import FormulaTestResult, LabFormula
from app_material.models import MaterialType, MetricCategory, TestConfig
from app_trial_production.models import (
    ProductionOrder, ProductionOrderFormulaDetail)

class MeanWritebackTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='wb_user', email='wb@test.local', password='x')
        self.project = Project.objects.create(name='项目W', manager=self.user)
        self.mt = MaterialType.objects.create(name='PA66')
        self.formula = LabFormula.objects.create(
            code='T-6000', name='配方', material_type=self.mt,
            project=self.project, creator=self.user, version=1)

        category = MetricCategory.objects.create(name='力学', order=1)
        self.tc_order = TestConfig.objects.create(
            category=category, name='拉伸强度', standard='ISO 527',
            data_type='NUMBER', unit='MPa', order=1)
        self.tc_manual = TestConfig.objects.create(
            category=category, name='人工评定', standard='内部',
            data_type='TEXT', unit='', order=2)
        self.tc_new = TestConfig.objects.create(
            category=category, name='冲击强度', standard='ISO 179',
            data_type='NUMBER', unit='kJ/m²', order=3)

        # 工单回写值（拉伸）
        order = ProductionOrder.objects.create(
            code='TP-6000', trial_code=self.formula.code, creator=self.user)
        ProductionOrderFormulaDetail.objects.create(
            production_order=order, formula=self.formula, planned_quantity=10)
        FormulaTestResult.objects.create(
            formula=self.formula, test_config=self.tc_order,
            production_order=order, value=Decimal('50.000'))
        # 纯手动录入值（人工评定），没有工单对应值
        FormulaTestResult.objects.create(
            formula=self.formula, test_config=self.tc_manual,
            production_order=None, value_text='合格')

        self.client.force_login(self.user)

    def _url(self):
        return reverse('project_formula_mean_writeback',
                       kwargs={'pk': self.project.pk, 'formula_pk': self.formula.pk})

    def _post(self, data):
        """带上表单标记字段 —— 视图靠它区分"用户删光了行"与"请求被裁剪"。"""
        payload = dict(data)
        payload['writeback_form'] = '1'
        return self.client.post(self._url(), payload)

    def _manual_value(self, test_config):
        obj = FormulaTestResult.objects.filter(
            formula=self.formula, test_config=test_config,
            production_order__isnull=True).first()
        return obj.value_text if obj else None

    def test_page_lists_manual_only_rows(self):
        """纯手动录入的测试项也要出现在表里，否则用户根本看不到它。"""
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '人工评定')
        self.assertContains(resp, '拉伸强度')

    def test_submitting_unrelated_row_keeps_manual_only_value(self):
        """提交不涉及的行时，纯手动录入的测试项必须原样保留。"""
        resp = self._post({
            f'num_{self.tc_order.pk}': '55.5',
        })
        self.assertEqual(resp.status_code, 302)

        self.assertEqual(self._manual_value(self.tc_manual), '合格',
                         '未出现在表单里的手动录入项不得被删除')
        agg = FormulaTestResult.objects.get(
            formula=self.formula, test_config=self.tc_order, production_order__isnull=True)
        self.assertEqual(agg.value, Decimal('55.5'))

    def test_clearing_value_removes_manual_entry(self):
        """清空某一项的值 = 移除该测试项的手动录入记录。"""
        resp = self._post({
            f'txt_{self.tc_manual.pk}': '',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(self._manual_value(self.tc_manual))

    def test_can_add_new_test_item(self):
        """新增行：提交一个此前不存在的测试项目。"""
        resp = self._post({
            f'num_{self.tc_new.pk}': '12.3',
        })
        self.assertEqual(resp.status_code, 302)
        created = FormulaTestResult.objects.filter(
            formula=self.formula, test_config=self.tc_new,
            production_order__isnull=True).first()
        self.assertIsNotNone(created, '新测试项目应被创建')
        self.assertEqual(created.value, Decimal('12.3'))

    def test_writeback_does_not_touch_order_results(self):
        """工单回写的结果不属于本页管辖范围，不得被改动。"""
        self._post({f'num_{self.tc_order.pk}': '1.0'})
        order_result = FormulaTestResult.objects.get(
            formula=self.formula, test_config=self.tc_order, production_order__isnull=False)
        self.assertEqual(order_result.value, Decimal('50.000'))

    def test_template_comments_do_not_leak_into_html(self):
        """Django 的 {# #} 不支持跨行：写成多行会原样输出到浏览器。

        这条纯粹是防回归 —— 其它测试都发现不了注释漏渲染。
        """
        html = self.client.get(self._url()).content.decode('utf-8')
        self.assertNotIn('{#', html)
        self.assertNotIn('#}', html)
        for fragment in ('data-persisted：', '与实验单编辑页的', '标记字段：', '记住本行原本'):
            self.assertNotIn(fragment, html, msg=f'模板注释泄漏到页面: {fragment}')

    def test_card_replicates_material_property_card(self):
        """卡片一比一复刻成品材料「物性指标」卡片的结构与样式约束。

        记录两个踩过的坑：
        - 套了 table-responsive（overflow-x:auto）会把 TomSelect 下拉面板裁掉；
        - 只调 .form-control/.form-select 管不到 TomSelect 另渲染的 .ts-control，
          结果选框尺寸/字号与普通输入框不一致。
        """
        html = self.client.get(self._url()).content.decode('utf-8')
        self.assertNotIn('table-responsive', html, '会裁掉下拉面板')
        self.assertIn('css/apps/app_project/test_result_writeback.css', html)
        self.assertIn('id="data-table"', html)
        self.assertIn('card-header bg-purple-lt', html)
        # 尺寸统一交给 #data-table 的 CSS 压紧，不混用 -sm
        self.assertNotIn('form-control-sm', html)
        self.assertNotIn('form-select-sm', html)

    def test_page_columns_match_formula_edit_card(self):
        """填写卡片的列与实验单编辑页的「测试结果」卡片对齐，另加各工单原始值。"""
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        for header in ('测试项目', '各工单原始值', '数值 / 结果', '测试日期', '备注', '删除'):
            self.assertContains(resp, header)
        # 对齐编辑页后的表格样式（原回写页用的是另一套 card-table table-sm small）
        self.assertContains(resp, 'table-bordered card-table text-nowrap table-sm text-center')

    def test_saves_test_date_and_remark(self):
        """测试日期与备注是编辑页有的字段，回写页必须一并保存。"""
        resp = self._post({
            f'num_{self.tc_order.pk}': '55.5',
            f'date_{self.tc_order.pk}': '2026-09-16',
            f'rem_{self.tc_order.pk}': '复测',
        })
        self.assertEqual(resp.status_code, 302)

        agg = FormulaTestResult.objects.get(
            formula=self.formula, test_config=self.tc_order, production_order__isnull=True)
        self.assertEqual(agg.test_date, date(2026, 9, 16))
        self.assertEqual(agg.remark, '复测')

    def test_select_type_gets_a_dropdown(self):
        """SELECT 型测试项要渲染成下拉（编辑页是三态，回写页原先只有两态）。"""
        select_config = TestConfig.objects.create(
            category=self.tc_order.category, name='阻燃等级', standard='UL94',
            data_type='SELECT', options_config='V-0,V-1,V-2', order=5)
        FormulaTestResult.objects.create(
            formula=self.formula, test_config=select_config,
            production_order=None, value_text='V-0')

        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'name="txt_{select_config.pk}"')
        self.assertContains(resp, '<option value="V-0" selected>')

    def test_select_type_value_is_saved(self):
        select_config = TestConfig.objects.create(
            category=self.tc_order.category, name='阻燃等级', standard='UL94',
            data_type='SELECT', options_config='V-0,V-1,V-2', order=6)
        resp = self._post({
            f'txt_{select_config.pk}': 'V-1',
        })
        self.assertEqual(resp.status_code, 302)
        saved = FormulaTestResult.objects.get(
            formula=self.formula, test_config=select_config, production_order__isnull=True)
        self.assertEqual(saved.value_text, 'V-1')

    def test_test_item_dropdown_matches_edit_page(self):
        """测试项目下拉要与实验单编辑页同款：form-select-search + 全部配置项。"""
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'form-select form-select-search writeback-config')
        # 选项文案用 TestConfig.__str__（编辑页也是这个），而不是光秃秃的 name
        self.assertContains(
            resp, f'<option value="{self.tc_order.pk}" selected>{self.tc_order}</option>')

    def test_changing_test_item_removes_old_record(self):
        """把某行的测试项目改成另一个 → 原测试项的手动录入记录必须一起移除。

        否则改完刷新，旧的测试项会因为"有手动录入值"又冒出一行。
        前端改下拉时会补上 orig_{新pk}={原pk} 隐藏域，这里照此构造。
        """
        resp = self._post({
            f'num_{self.tc_new.pk}': '12.3',
            f'orig_{self.tc_new.pk}': str(self.tc_manual.pk),
        })
        self.assertEqual(resp.status_code, 302)

        self.assertIsNone(self._manual_value(self.tc_manual),
                          '原测试项(人工评定)的记录应被移除')
        created = FormulaTestResult.objects.get(
            formula=self.formula, test_config=self.tc_new, production_order__isnull=True)
        self.assertEqual(created.value, Decimal('12.3'))

    def test_renaming_one_row_does_not_touch_other_unposted_rows(self):
        """改一行不得殃及本次没提交的行（并发下别人新增的项会在这里被误删）。"""
        other = TestConfig.objects.create(
            category=self.tc_order.category, name='色差', standard='内部',
            data_type='TEXT', order=7)
        FormulaTestResult.objects.create(
            formula=self.formula, test_config=other, production_order=None, value_text='合格')

        self._post({
            f'num_{self.tc_new.pk}': '12.3',
            f'orig_{self.tc_new.pk}': str(self.tc_manual.pk),
        })

        self.assertIsNone(self._manual_value(self.tc_manual), '被改的那行应移除原记录')
        self.assertEqual(self._manual_value(other), '合格', '未提交的行不得被牵连')

    def test_post_without_form_marker_is_rejected(self):
        """缺少表单标记的请求不得清空手动录入数据。"""
        resp = self.client.post(self._url(), {})  # 无 writeback_form
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self._manual_value(self.tc_manual), '合格',
                         '被拒时不得删除任何记录')
