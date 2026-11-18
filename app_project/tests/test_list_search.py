"""项目列表按编码搜索：后台 changelist 与前台 ProjectFilter。"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app_project.admin import ProjectAdmin
from app_project.models import Project, ProjectNode
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

    def test_project_filter_by_run_status(self):
        self.hit.is_terminated = True
        self.hit.save(update_fields=['is_terminated'])
        paused = Project.objects.create(code='PX-PAUSE', name='暂停项目', manager=self.hit.manager)
        init = paused.nodes.get(stage='INIT')
        init.status = 'PAUSED'
        init.save()
        # 后面的节点暂停不算，当前节点仍是未开始的立项
        later = self.other.nodes.get(stage='RND')
        later.status = 'PAUSED'
        later.save()
        qs = Project.objects.all()

        self.assertEqual(
            set(ProjectFilter({'run_status': 'terminated'}, queryset=qs).qs),
            {self.hit},
        )
        self.assertEqual(
            set(ProjectFilter({'run_status': 'paused'}, queryset=qs).qs),
            {paused},
        )
        self.assertEqual(
            set(ProjectFilter({'run_status': 'doing'}, queryset=qs).qs),
            {self.other},
        )
        self.assertEqual(set(ProjectFilter({}, queryset=qs).qs), {self.hit, self.other, paused})

    def test_project_filter_stale_days_uses_current_node(self):
        manager = self.hit.manager
        stale = Project.objects.create(code='PX-STALE', name='超期项目', manager=manager)
        fresh = Project.objects.create(code='PX-FRESH', name='刚更新', manager=manager)
        terminated = Project.objects.create(code='PX-STOP', name='已终止超期', manager=manager)
        done = Project.objects.create(code='PX-DONE', name='已完成超期', manager=manager)
        later_old = Project.objects.create(code='PX-LATER', name='后续节点旧', manager=manager)
        old = timezone.now() - timedelta(days=31)

        def age(project, stage):
            ProjectNode.objects.filter(project=project, stage=stage).update(updated_at=old)

        age(stale, 'INIT')
        age(fresh, 'RND')
        age(terminated, 'INIT')
        age(done, 'INIT')
        age(later_old, 'RND')
        Project.objects.filter(pk=terminated.pk).update(is_terminated=True)
        Project.objects.filter(pk=done.pk).update(progress_percent=100)

        found = set(ProjectFilter({'stale_days': 30}, queryset=Project.objects.all()).qs)
        self.assertIn(stale, found)
        self.assertNotIn(fresh, found)
        self.assertNotIn(terminated, found)
        self.assertNotIn(done, found)
        self.assertNotIn(later_old, found)
        self.assertNotIn(self.other, found)
