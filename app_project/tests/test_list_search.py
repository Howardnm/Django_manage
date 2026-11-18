"""项目列表按编码搜索：后台 changelist 与前台 ProjectFilter。"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app_project.admin import ProjectAdmin
from app_project.models import Project
from app_project.utils.filters import ProjectFilter

User = get_user_model()


class ProjectSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username='search_admin', email='search_admin@test.local', password='x',
        )
        manager = User.objects.create_user(
            username='search_mgr', email='search_mgr@test.local', password='x',
        )
        cls.hit = Project.objects.create(code='PX-10086', name='编码项目', manager=manager)
        cls.other = Project.objects.create(code='PX-99999', name='另一个项目', manager=manager)

    def test_admin_search_fields_include_code(self):
        self.assertIn('code', ProjectAdmin.search_fields)
        self.assertEqual(ProjectAdmin.list_display[0], 'code')

    def test_admin_changelist_finds_project_by_code_fragment(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('admin:app_project_project_changelist'), {'q': '10086'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '编码项目')
        self.assertNotContains(resp, '另一个项目')

    def test_project_filter_matches_code_and_name(self):
        by_code = set(ProjectFilter({'q': '10086'}, queryset=Project.objects.all()).qs)
        by_name = set(ProjectFilter({'q': '另一个'}, queryset=Project.objects.all()).qs)
        self.assertEqual(by_code, {self.hit})
        self.assertEqual(by_name, {self.other})
