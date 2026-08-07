import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app_form_management.models import FormTemplate, FormSubmission
from app_form_management.services import (
    assign_submission_code,
    generate_form_code,
    get_template_code_config,
)

User = get_user_model()


def make_template(with_config=True, **cfg_overrides):
    cfg = {
        'enabled': True,
        'prefix': 'IQC',
        'dateFormat': '%Y%m%d',
        'separator': '-',
        'seqLength': 3,
        'targetField': 'inspection_code',
    }
    cfg.update(cfg_overrides)
    return FormTemplate.objects.create(
        name='来料检验',
        form_config=[],
        form_option={'codeConfig': cfg} if with_config else {},
        created_by=None,
    )


class TemplateCodeConfigTest(TestCase):
    def test_config_disabled_returns_none(self):
        t = make_template(with_config=False)
        self.assertIsNone(get_template_code_config(t))

    def test_config_enabled_returns_dict(self):
        t = make_template()
        cfg = get_template_code_config(t)
        self.assertEqual(cfg['prefix'], 'IQC')
        self.assertEqual(cfg['seqLength'], 3)


class GenerateFormCodeTest(TestCase):
    def test_full_code(self):
        t = make_template()
        code = generate_form_code(t, 1)
        self.assertRegex(code, r'^IQC\d{8}-\d{3}$')

    def test_no_date_config(self):
        t = make_template(dateFormat='')
        self.assertEqual(generate_form_code(t, 7), 'IQC-007')

    def test_hyphen_date_format_keeps_separator(self):
        t = make_template(dateFormat='%Y-%m-%d')
        code = generate_form_code(t, 2)
        self.assertRegex(code, r'^IQC\d{4}-\d{2}-\d{2}-\d{3}$')


class AssignSubmissionCodeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('tester', password='x')

    def _create_submission(self, template):
        return FormSubmission.objects.create(
            template=template,
            submitted_by=self.user,
            form_data={'inspector': '张三'},
            status='SUBMITTED',
        )

    def test_assigns_code_on_submit(self):
        t = make_template()
        sub = self._create_submission(t)
        ok = assign_submission_code(sub)
        self.assertTrue(ok)
        self.assertRegex(sub.code, r'^IQC\d{8}-001$')
        # 编码写入目标字段
        self.assertEqual(sub.form_data['inspection_code'], sub.code)

    def test_sequence_increments_per_day(self):
        t = make_template()
        sub1 = self._create_submission(t)
        sub2 = self._create_submission(t)
        assign_submission_code(sub1)
        assign_submission_code(sub2)
        seq1 = int(re.search(r'(\d+)$', sub1.code).group(1))
        seq2 = int(re.search(r'(\d+)$', sub2.code).group(1))
        self.assertEqual(seq2, seq1 + 1)

    def test_no_config_no_code(self):
        t = make_template(with_config=False)
        sub = self._create_submission(t)
        ok = assign_submission_code(sub)
        self.assertFalse(ok)
        self.assertEqual(sub.code, '')

    def test_idempotent_when_code_exists(self):
        t = make_template()
        sub = self._create_submission(t)
        assign_submission_code(sub)
        original = sub.code
        assign_submission_code(sub)
        sub.refresh_from_db()
        self.assertEqual(sub.code, original)

    def test_revision_rewrites_target_field(self):
        t = make_template()
        sub = self._create_submission(t)
        assign_submission_code(sub)
        # 模拟退回修订后重新提交：code 保留，form_data 被用户覆盖为空
        sub.form_data = {'inspector': '李四'}
        sub.status = 'SUBMITTED'
        sub.save()
        assign_submission_code(sub)
        sub.refresh_from_db()
        self.assertEqual(sub.code, 'IQC' + sub.created_at.strftime('%Y%m%d') + '-001')
        self.assertEqual(sub.form_data['inspection_code'], sub.code if sub.code else '')


class FormTemplateStepMethodsTest(TestCase):
    """验证步骤相关方法对表格/分组等嵌套字段的递归处理。"""

    def _nested_template(self):
        # 表格布局（fcTable）：children 中嵌套了不同步骤的字段
        # 顶层另有普通字段
        return FormTemplate.objects.create(
            name='嵌套表单',
            form_config=[
                {
                    'type': 'fcTable',
                    'props': {'rule': {'row': 2, 'col': 2}},
                    'children': [
                        {'type': 'input', 'field': 'tbl_a', 'title': '表内A', 'props': {'step': 1}},
                        {'type': 'input', 'field': 'tbl_b', 'title': '表内B', 'props': {'step': 2}},
                    ],
                },
                {'type': 'input', 'field': 'top_field', 'title': '顶层', 'props': {'step': 2}},
                {'type': 'fcRow', 'props': {}, 'children': [
                    {'type': 'col', 'props': {}, 'children': [
                        {'type': 'select', 'field': 'nested_sel', 'title': '列内', 'props': {'step': 3}},
                    ]},
                ]},
            ],
        )

    def test_get_field_step_map_includes_nested(self):
        t = self._nested_template()
        m = t.get_field_step_map()
        self.assertEqual(m['tbl_a'], 1)
        self.assertEqual(m['tbl_b'], 2)
        self.assertEqual(m['top_field'], 2)
        self.assertEqual(m['nested_sel'], 3)

    def test_get_step_fields_includes_nested(self):
        t = self._nested_template()
        self.assertEqual(sorted(t.get_step_fields(1)), ['tbl_a'])
        self.assertEqual(sorted(t.get_step_fields(2)), ['tbl_b', 'top_field'])
        self.assertEqual(t.get_step_fields(3), ['nested_sel'])

    def test_step_groups_reflects_nested_max_step(self):
        t = self._nested_template()
        groups = t.step_groups
        self.assertEqual([g['step'] for g in groups], [1, 2, 3])
        self.assertTrue(t.is_multi_step)


class FormSubmissionViewIntegrationTest(TestCase):
    """端到端：通过真实 POST 提交链路验证编码生成。"""

    def setUp(self):
        self.superuser = User.objects.create_superuser('admin', password='x')
        self.template = make_template()
        self.client.force_login(self.superuser)

    def test_post_submit_generates_code(self):
        resp = self.client.post(
            reverse('form_submission_fill', kwargs={'template_pk': self.template.pk}),
            data={
                'form_data': {'inspector': '张三'},
                'status': 'SUBMITTED',
                'remark': '',
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get('status'), 'success')
        sub = FormSubmission.objects.get(template=self.template)
        self.assertRegex(sub.code, r'^IQC\d{8}-001$')
        self.assertEqual(sub.form_data['inspection_code'], sub.code)

    def test_post_draft_no_code(self):
        resp = self.client.post(
            reverse('form_submission_fill', kwargs={'template_pk': self.template.pk}),
            data={
                'form_data': {'inspector': '张三'},
                'status': 'DRAFT',
                'remark': '',
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        sub = FormSubmission.objects.get(template=self.template)
        self.assertEqual(sub.code, '')