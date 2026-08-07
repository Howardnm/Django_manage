"""回归测试：resolve_form_target 辅助函数与 MyDraftsView/MySubmissionsView 重构。

覆盖改动：
- app_form_management/registry.py 新增 resolve_form_target（替代原先 view 内联解析）
- app_form_management/views.py 的 MyDraftsView / MySubmissionsView 改用该 helper
"""
from django.test import TestCase
from django.test import Client
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

from app_form_management.models import FormSubmission, FormTemplate
from app_form_management.registry import resolve_form_target
from app_project.models import Project

User = get_user_model()


class ResolveFormTargetTest(TestCase):
    """resolve_form_target 辅助函数的单元测试。"""

    def setUp(self):
        self.user = User.objects.create_user(username='t_user', password='x')
        self.template = FormTemplate.objects.create(name='测试表单')
        self.project = Project.objects.create(
            name='某某新品项目', manager=self.user,
        )

    def _submission(self, target=None):
        kw = dict(template=self.template, submitted_by=self.user)
        if target is not None:
            kw['content_type'] = ContentType.objects.get_for_model(type(target))
            kw['object_id'] = target.pk
        return FormSubmission.objects.create(**kw)

    def test_no_association_returns_placeholders(self):
        """无关联对象时返回占位符与空 URL。"""
        s = self._submission()
        self.assertEqual(resolve_form_target(s), ('—', '—', None))

    def test_project_association_resolves_module_content_url(self):
        """关联 Project 时返回 '项目' 模块标签、项目名称、详情链接。"""
        s = self._submission(self.project)
        module, display, url = resolve_form_target(s)
        self.assertEqual(module, '项目')
        self.assertEqual(display, '某某新品项目')
        self.assertIsNotNone(url)
        self.assertIn(f'/project/{self.project.pk}', url)


class FormListViewsRegressionTest(TestCase):
    """重构后 MyDraftsView / MySubmissionsView 仍正确附加 target_module/display/url。"""

    def setUp(self):
        self.su = User.objects.create_superuser(
            username='list_su', password='x', email='a@b.com'
        )
        self.client = Client()
        self.client.force_login(self.su)
        self.template = FormTemplate.objects.create(name='测试表单')
        self.project = Project.objects.create(
            name='回归项目', manager=self.su,
        )
        self.ct = ContentType.objects.get_for_model(Project)

    def test_my_drafts_still_resolves_target(self):
        FormSubmission.objects.create(
            template=self.template, submitted_by=self.su, status='DRAFT',
            content_type=self.ct, object_id=self.project.pk,
        )
        resp = self.client.get('/forms/my/drafts/')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('项目', body)
        self.assertIn('回归项目', body)

    def test_my_submissions_still_resolves_target(self):
        FormSubmission.objects.create(
            template=self.template, submitted_by=self.su, status='SUBMITTED',
            content_type=self.ct, object_id=self.project.pk,
        )
        resp = self.client.get('/forms/my/submissions/')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('项目', body)
        self.assertIn('回归项目', body)