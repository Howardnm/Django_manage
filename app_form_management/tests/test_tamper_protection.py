"""后端防篡改回归测试——前端只读/禁用组件仅表现层控制，后端必须独立校验。

覆盖：
1. WorkflowService._merge_step_form_data：多步骤审批只能写入当前步骤字段，
   越权字段（其他步骤）与伪字段被静默丢弃。
2. 单步骤流程：仅允许已配置字段，伪字段被丢弃。
3. FormSubmissionCreateView.post：初始提交的 form_data 仅保留已配置字段名，
   阻断任意字段注入，同时不破坏修订重提（保留其他步骤已合并字段）。
"""
import types

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app_form_management.models import FormSubmission, FormTemplate
from app_workflow.services import WorkflowService
from app_workflow.models import WorkflowDefinition

User = get_user_model()


def make_multi_step_template():
    """step1: s1_a, s1_b；step2: s2_a（嵌套在表格内）；step3: s3_a"""
    return FormTemplate.objects.create(
        name='多步骤防篡改',
        form_config=[
            {'type': 'input', 'field': 's1_a', 'title': '步骤1A', 'props': {'step': 1}},
            {'type': 'input', 'field': 's1_b', 'title': '步骤1B', 'props': {'step': 1}},
            {'type': 'fcTable', 'props': {'rule': {'row': 1, 'col': 1}}, 'children': [
                {'type': 'input', 'field': 's2_a', 'title': '步骤2A', 'props': {'step': 2}},
            ]},
            {'type': 'select', 'field': 's3_a', 'title': '步骤3A', 'props': {'step': 3}},
        ],
        created_by=None,
    )


def make_workflow_multi_step_template():
    """多步 + 关联流程 → 发起人限制为只能写步骤1"""
    wf = WorkflowDefinition.objects.create(
        name='测试流程', bpmn_xml='<definitions/>')
    return FormTemplate.objects.create(
        name='工作流多步防篡改',
        workflow=wf,
        form_config=[
            {'type': 'input', 'field': 's1_a', 'title': '步骤1A', 'props': {'step': 1}},
            {'type': 'input', 'field': 's2_a', 'title': '步骤2A', 'props': {'step': 2}},
            {'type': 'input', 'field': 's3_a', 'title': '步骤3A', 'props': {'step': 3}},
        ],
        created_by=None,
    )


def make_single_step_template():
    return FormTemplate.objects.create(
        name='单步骤防篡改',
        form_config=[
            {'type': 'input', 'field': 'f1', 'title': '字段1'},
            {'type': 'input', 'field': 'f2', 'title': '字段2'},
        ],
        created_by=None,
    )


def make_submission(template, user, **form_data):
    return FormSubmission.objects.create(
        template=template,
        submitted_by=user,
        form_data=form_data or {},
        status='SUBMITTED',
    )


class MergeStepFormDataTest(TestCase):
    """WorkflowService._merge_step_form_data 白名单过滤"""

    def setUp(self):
        self.user = User.objects.create_user('tester', password='x')

    def _merge(self, submission, form_step, step_form_data):
        task = types.SimpleNamespace(form_step=form_step)
        WorkflowService._merge_step_form_data(submission, task, {'step_form_data': step_form_data})
        submission.refresh_from_db()
        return submission.form_data

    def test_multi_step_only_current_step_allowed(self):
        t = make_multi_step_template()
        sub = make_submission(t, self.user, s1_a='原始')
        result = self._merge(sub, 2, {
            's2_a': '步骤2新值',   # 当前步骤 → 合并
            's1_a': '被篡改',      # 其他步骤 → 丢弃
            's3_a': '被篡改',      # 其他步骤 → 丢弃
            'phantom': '伪字段',   # 不存在 → 丢弃
        })
        self.assertEqual(result['s2_a'], '步骤2新值')
        self.assertEqual(result['s1_a'], '原始')  # 未被篡改
        self.assertNotIn('s3_a', result)
        self.assertNotIn('phantom', result)

    def test_multi_step_step3_nested_table_field_used(self):
        # 回归：表格内字段（s2_a）也能被正确识别为步骤2白名单
        t = make_multi_step_template()
        sub = make_submission(t, self.user)
        result = self._merge(sub, 2, {'s2_a': 'ok', 's1_a': 'no'})
        self.assertEqual(result.get('s2_a'), 'ok')
        self.assertIsNone(result.get('s1_a'))

    def test_multi_step_step1_merge(self):
        t = make_multi_step_template()
        sub = make_submission(t, self.user, s1_a='a', s2_a='x')
        result = self._merge(sub, 1, {'s1_a': 'new', 's2_a': '改'})
        self.assertEqual(result['s1_a'], 'new')
        self.assertEqual(result['s2_a'], 'x')  # 步骤2字段未被污染

    def test_single_step_allows_configured_fields(self):
        t = make_single_step_template()
        sub = make_submission(t, self.user)
        result = self._merge(sub, None, {'f1': 'aa', 'f2': 'bb', 'phantom': 'x'})
        self.assertEqual(result['f1'], 'aa')
        self.assertEqual(result['f2'], 'bb')
        self.assertNotIn('phantom', result)

    def test_empty_step_form_data_noop(self):
        t = make_single_step_template()
        sub = make_submission(t, self.user, f1='keep')
        WorkflowService._merge_step_form_data(
            sub, types.SimpleNamespace(form_step=None), {})
        sub.refresh_from_db()
        self.assertEqual(sub.form_data['f1'], 'keep')

    def test_non_submission_related_ignored(self):
        t = make_single_step_template()
        sub = make_submission(t, self.user)
        # 传入非 FormSubmission 对象应安全忽略，不抛异常
        WorkflowService._merge_step_form_data(
            object(), types.SimpleNamespace(form_step=None),
            {'step_form_data': {'f1': 'x'}})
        sub.refresh_from_db()
        self.assertEqual(sub.form_data, {})


class InitialSubmitFilterTest(TestCase):
    """FormSubmissionCreateView.post 对 form_data 的字段级过滤"""

    def setUp(self):
        self.superuser = User.objects.create_superuser('admin', password='x')
        self.client.force_login(self.superuser)

    def test_post_drops_phantom_fields(self):
        t = make_single_step_template()
        resp = self.client.post(
            reverse('form_submission_fill', kwargs={'template_pk': t.pk}),
            data={
                'form_data': {'f1': 'ok', 'phantom': '注入'},
                'status': 'SUBMITTED',
                'remark': '',
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        sub = FormSubmission.objects.get(template=t)
        self.assertEqual(sub.form_data, {'f1': 'ok'})

    def test_post_multi_step_keeps_configured_fields(self):
        # 非工作流多步模板：仅过滤伪字段，已配置字段（含各步骤）保留
        t = make_multi_step_template()
        resp = self.client.post(
            reverse('form_submission_fill', kwargs={'template_pk': t.pk}),
            data={
                'form_data': {
                    's1_a': '一', 's2_a': '二', 's3_a': '三',
                    'phantom': '注入',
                },
                'status': 'SUBMITTED',
                'remark': '',
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        sub = FormSubmission.objects.get(template=t)
        self.assertEqual(sub.form_data['s1_a'], '一')
        self.assertEqual(sub.form_data['s2_a'], '二')
        self.assertEqual(sub.form_data['s3_a'], '三')
        self.assertNotIn('phantom', sub.form_data)

    def test_workflow_restricted_first_submit_only_step1(self):
        # 发起人严格限制：关联流程的多步表单，首次提交只能写步骤1
        t = make_workflow_multi_step_template()
        resp = self.client.post(
            reverse('form_submission_fill', kwargs={'template_pk': t.pk}),
            data={
                'form_data': {
                    's1_a': '我是步骤1',
                    's2_a': '篡改步骤2', 's3_a': '篡改步骤3',
                    'phantom': '伪字段',
                },
                'status': 'SUBMITTED',
                'remark': '',
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        sub = FormSubmission.objects.get(template=t)
        self.assertEqual(sub.form_data, {'s1_a': '我是步骤1'})
        self.assertNotIn('s2_a', sub.form_data)
        self.assertNotIn('s3_a', sub.form_data)
        self.assertNotIn('phantom', sub.form_data)

    def test_workflow_restricted_revision_preserves_other_steps(self):
        # 修订重提：步骤2/3 已有值保留（来自 DB 既有数据），步骤1 以本次为准，
        # 请求中伪造的步骤2/3 及伪字段被丢弃
        t = make_workflow_multi_step_template()
        sub = FormSubmission.objects.create(
            template=t, submitted_by=self.superuser,
            form_data={'s1_a': '旧步骤1', 's2_a': '审批人填的2', 's3_a': '审批人填的3'},
            status='SUBMITTED',
        )
        resp = self.client.post(
            reverse('form_submission_edit', kwargs={
                'template_pk': t.pk, 'submission_pk': sub.pk,
            }),
            data={
                'form_data': {
                    's1_a': '新步骤1',
                    's2_a': '伪造2', 's3_a': '伪造3',
                    'phantom': '伪字段',
                },
                'status': 'SUBMITTED',
                'remark': '',
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.form_data['s1_a'], '新步骤1')
        self.assertEqual(sub.form_data['s2_a'], '审批人填的2')  # 保留，未被篡改
        self.assertEqual(sub.form_data['s3_a'], '审批人填的3')  # 保留，未被篡改
        self.assertNotIn('phantom', sub.form_data)

    def test_post_non_dict_form_data_emptied(self):
        t = make_single_step_template()
        resp = self.client.post(
            reverse('form_submission_fill', kwargs={'template_pk': t.pk}),
            data={'form_data': 'not-a-dict', 'status': 'SUBMITTED', 'remark': ''},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        sub = FormSubmission.objects.get(template=t)
        self.assertEqual(sub.form_data, {})