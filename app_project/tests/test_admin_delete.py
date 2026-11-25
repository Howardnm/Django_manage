"""后台删除项目：变更记录随项目级联，但不能在自己的菜单里删。"""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app_project.admin import ProjectAdmin, ProjectSalesMemberInline
from app_project.models import (
    BusinessSegment, FailureReason, FeedbackType, Project, ProjectFieldChange,
    ProjectSalesMember,
)

User = get_user_model()


class ProjectAdminDeleteTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            'proj-admin', 'proj-admin@test.local', 'x',
        )
        self.client.force_login(self.admin_user)
        manager = User.objects.create_user('proj-mgr', 'proj-mgr@test.local', 'x')
        self.project = Project.objects.create(name='待删项目', code='DEL-1', manager=manager)
        self.change = ProjectFieldChange.objects.create(
            project=self.project,
            name='待删项目',
            submitted_by=self.admin_user,
            submission_comment='改个名字',
        )
        self.reason = FailureReason.objects.create(name='色差')

    def test_delete_project_cascades_field_change_and_keeps_lookup(self):
        url = reverse('admin:app_project_project_delete', args=[self.project.pk])
        confirm = self.client.get(url)
        self.assertEqual(confirm.status_code, 200)
        self.assertFalse(confirm.context['perms_lacking'])

        response = self.client.post(url, {'post': 'yes'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        self.assertFalse(ProjectFieldChange.objects.filter(pk=self.change.pk).exists())
        self.assertTrue(FailureReason.objects.filter(pk=self.reason.pk).exists())

    def test_field_change_cannot_be_deleted_on_its_own(self):
        url = reverse('admin:app_project_projectfieldchange_delete', args=[self.change.pk])
        response = self.client.post(url, {'post': 'yes'})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ProjectFieldChange.objects.filter(pk=self.change.pk).exists())

    def test_sales_member_inline_and_lookups_registered(self):
        self.assertIn(ProjectSalesMemberInline, ProjectAdmin.inlines)
        self.assertFalse(admin.site.is_registered(ProjectSalesMember))
        for model in (FailureReason, FeedbackType, BusinessSegment):
            self.assertTrue(admin.site.is_registered(model))
