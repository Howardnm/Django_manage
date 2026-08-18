"""回归测试：个人工作台卡片展示「关联内容」及列精简。

覆盖改动：
- app_panel/views/PersonalWorkspaceView.py 解析并附加关联字段
- templates/apps/app_panel/personal_workspace.html 新增「关联内容」列、移除流程/任务名称列
- 五组列表合并为表单/流程两张大卡，用 card-header-tabs 切换
"""
from django.test import TestCase
from django.test import Client
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from app_form_management.models import FormSubmission, FormTemplate
from app_project.models import Project
from app_workflow.models import WorkflowDefinition, WorkflowInstance, WorkflowTask

User = get_user_model()


class PersonalWorkspaceViewRegressionTest(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser(
            username='ws_su', password='x', email='a@b.com'
        )
        self.client = Client()
        self.client.force_login(self.su)
        self.template = FormTemplate.objects.create(name='测试表单')
        self.project = Project.objects.create(
            name='某某新品项目', manager=self.su,
        )
        self.ct = ContentType.objects.get_for_model(Project)
        self.defn = WorkflowDefinition.objects.create(name='审批流程', bpmn_xml='')

    def _draft(self):
        return FormSubmission.objects.create(
            template=self.template, submitted_by=self.su, status='DRAFT',
            content_type=self.ct, object_id=self.project.pk,
        )

    def _submission(self):
        return FormSubmission.objects.create(
            template=self.template, submitted_by=self.su, status='SUBMITTED',
            content_type=self.ct, object_id=self.project.pk,
        )

    def _instance(self):
        return WorkflowInstance.objects.create(
            definition=self.defn, started_by=self.su,
            content_type=self.ct, object_id=self.project.pk,
        )

    def _task(self, instance, task_name, status, spiff_id):
        return WorkflowTask.objects.create(
            instance=instance, task_name=task_name, spiff_task_id=spiff_id,
            status=status, assigned_to=self.su if status != 'PENDING' else self.su,
        )

    def test_workspace_renders_all_cards_with_associated_content(self):
        """五张卡片均渲染，且「关联内容」列显示 模块 - 名称。"""
        self._draft()
        self._submission()
        inst = self._instance()
        self._task(inst, '待审任务', 'PENDING', 't1')
        self._task(inst, '已办任务', 'COMPLETED', 't2')

        resp = self.client.get(reverse('personal_workspace'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')

        # 卡片标题（现为 tab 文案）
        for title in ('我的表单草稿', '我提交的表单', '我已发的流程', '待办任务', '已办任务'):
            self.assertIn(title, body, f'缺少卡片标题 {title}')

        # 两张大卡 + Tabler tab 头
        self.assertEqual(body.count('card-header-tabs'), 2)
        self.assertIn('id="ws-form-drafts"', body)
        self.assertIn('id="ws-form-submissions"', body)
        self.assertIn('id="ws-wf-pending"', body)
        self.assertIn('id="ws-wf-completed"', body)
        self.assertIn('id="ws-wf-initiated"', body)
        self.assertIn('tab-pane active show', body)

        # 关联内容列存在
        self.assertIn('关联内容', body)

        # 关联内容以「模块 - 名称」展示
        self.assertIn('项目 - 某某新品项目', body)

        # 精简后的列：移除流程名称/任务名称/所属流程
        self.assertNotIn('流程名称', body)
        self.assertNotIn('任务名称', body)
        self.assertNotIn('所属流程', body)

    def test_form_card_keeps_template_name(self):
        """表单卡片保留「表单模板」列（未被精简）。"""
        self._draft()
        resp = self.client.get(reverse('personal_workspace'))
        body = resp.content.decode('utf-8')
        self.assertIn('表单模板', body)
        self.assertIn('测试表单', body)

    def test_no_panel_access_fails_closed(self):
        """无看板模块权限的用户被重定向（L1/L2 fail-closed），而非渲染卡片。"""
        anon = User.objects.create_user(username='no_perm', password='x')
        c = Client()
        c.force_login(anon)
        resp = c.get(reverse('personal_workspace'))
        self.assertEqual(resp.status_code, 302)
        body = resp.content.decode('utf-8')
        self.assertNotIn('关联内容', body)