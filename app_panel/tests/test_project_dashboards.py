"""项目全景看板、项目统计看板：补齐模板缺的上下文，并按当前节点口径分桶。"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app_panel.views.ProjectStatisticsView import STAT_KEYS
from app_project.models import Project, ProjectNode, ProjectStage
from app_user.models import Department, WorkGroup

User = get_user_model()


class DashboardFixtureMixin:
    def setUp(self):
        self.su = User.objects.create_superuser(
            username='panel_su', password='x', email='panel-su@test.dev',
        )
        self.client.force_login(self.su)

    def _project(self, code, manager=None):
        return Project.objects.create(
            code=code,
            name=code,
            manager=manager or self.su,
        )


class ProjectOverviewDashboardTests(DashboardFixtureMixin, TestCase):
    def test_stage_chart_keeps_mass_track_projects(self):
        self._project('P-FRESH')
        done = self._project('P-DONE')
        for node in done.nodes.exclude(stage__in=ProjectStage.non_progress_codes()):
            node.status = 'DONE'
            node.save()
        done.refresh_from_db()
        self.assertEqual(done.current_stage, ProjectStage.MASS_TRACK)

        counts = self.client.get(reverse('project_overview')).context['stats']['stage_counts']
        self.assertEqual(counts['① 项目立项'], 1)
        self.assertEqual(counts['📌 量产过程跟踪'], 1)
        self.assertNotIn('🎗️客户意见', counts)
        self.assertEqual(sum(counts.values()), 2)

    def test_stage_counts_are_not_split_by_created_at(self):
        first = self._project('P-EARLY')
        second = self._project('P-LATE')
        Project.objects.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(days=5))
        Project.objects.filter(pk=second.pk).update(created_at=timezone.now() - timedelta(days=1))

        counts = self.client.get(reverse('project_overview')).context['stats']['stage_counts']
        self.assertEqual(counts['① 项目立项'], 2)

    def test_end_date_includes_projects_created_that_day(self):
        self._project('P-TODAY')
        today = timezone.localdate().isoformat()
        response = self.client.get(reverse('project_overview'), {
            'start_date': today,
            'end_date': today,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '项目全景看板')
        self.assertEqual(response.context['stats']['total_all'], 1)

    def test_multi_round_pilot_and_group_stats(self):
        dept = Department.objects.create(name='研发中心')
        group = WorkGroup.objects.create(name='配方组', department=dept)
        group.members.add(self.su)

        active = self._project('P-ROUND')
        ProjectNode.objects.create(
            project=active,
            stage=ProjectStage.PILOT,
            round=2,
            order=50,
            status='DOING',
        )
        terminated = self._project('P-TERM')
        init = terminated.nodes.get(stage=ProjectStage.INIT)
        init.status = 'TERMINATED'
        init.save()

        response = self.client.get(reverse('project_overview'))
        stats = response.context['stats']
        rounds = {item['p'].pk: item['round'] for item in stats['multi_round_pilot']}
        self.assertEqual(rounds[active.pk], 2)
        self.assertNotIn(terminated.pk, rounds)

        group = stats['group_stats']['[研发中心] 配方组']
        self.assertEqual(group['total'], 2)
        self.assertEqual(group['terminated'], 1)
        self.assertEqual(group['active'], 1)
        self.assertNotIn('研发中心', stats['group_stats'])

    def test_member_load_includes_up_to_three_projects(self):
        for i in range(4):
            project = self._project(f'P-M{i}')
            Project.objects.filter(pk=project.pk).update(
                created_at=timezone.now() - timedelta(days=i + 1)
            )
        response = self.client.get(reverse('project_overview'))
        row = response.context['member_stats_list'][0]
        self.assertEqual(row['name'], 'panel_su')
        self.assertEqual(row['project_count'], 4)
        self.assertEqual(len(row['projects']), 3)
        self.assertTrue(all(project.name for project in row['projects']))

    def test_stagnant_row_uses_current_open_node(self):
        project = self._project('P-STALL')
        init = project.nodes.get(stage=ProjectStage.INIT)
        init.status = 'DONE'
        init.save()
        rnd = project.nodes.get(stage=ProjectStage.RND)
        ProjectNode.objects.filter(pk=rnd.pk).update(
            status='AWAITING_APPROVAL',
            updated_at=timezone.now() - timedelta(days=40),
        )

        response = self.client.get(reverse('project_overview'))
        stagnant = response.context['stats']['stagnant_30d']
        self.assertEqual(len(stagnant), 1)
        self.assertEqual(stagnant[0]['p'].pk, project.pk)
        self.assertEqual(stagnant[0]['node'].stage, ProjectStage.RND)
        self.assertEqual(stagnant[0]['node'].status, 'AWAITING_APPROVAL')
        self.assertGreaterEqual(stagnant[0]['days'], 30)

    def test_paused_is_split_out_of_active(self):
        doing = self._project('P-DOING')
        paused = self._project('P-PAUSE')
        paused.nodes.filter(stage=ProjectStage.INIT).update(status='PAUSED')
        later_paused = self._project('P-LATER')
        later_paused.nodes.filter(stage=ProjectStage.PILOT).update(status='PAUSED')
        done = self._project('P-DONE')
        for node in done.nodes.exclude(stage__in=ProjectStage.non_progress_codes()):
            node.status = 'DONE'
            node.save()
        done.nodes.filter(stage=ProjectStage.MASS_TRACK).update(status='PAUSED')
        terminated = self._project('P-TERM')
        init = terminated.nodes.get(stage=ProjectStage.INIT)
        init.status = 'TERMINATED'
        init.save()

        response = self.client.get(reverse('project_overview'))
        stats = response.context['stats']
        self.assertEqual(stats['total_all'], 5)
        self.assertEqual(stats['total_paused'], 1)
        self.assertEqual(stats['total_active'], 2)
        self.assertEqual(stats['total_completed'], 1)
        self.assertEqual(stats['total_terminated'], 1)
        self.assertEqual(
            stats['total_active'] + stats['total_paused'] + stats['total_completed'] + stats['total_terminated'],
            stats['total_all'],
        )
        self.assertEqual(stats['total_unfinished'], stats['total_active'] + stats['total_paused'])
        self.assertContains(response, '暂停')
        self.assertFalse(doing.is_paused)
        self.assertFalse(later_paused.is_paused)

    def test_warning_table_paginates_inside_the_card(self):
        for i in range(9):
            project = self._project(f'P-W{i}')
            init = project.nodes.get(stage=ProjectStage.INIT)
            init.status = 'DONE'
            init.save()
            rnd = project.nodes.get(stage=ProjectStage.RND)
            ProjectNode.objects.filter(pk=rnd.pk).update(
                status='DOING',
                updated_at=timezone.now() - timedelta(days=40),
            )

        response = self.client.get(reverse('project_overview'))
        self.assertEqual(len(response.context['warning_rows']), 9)
        for i in range(9):
            self.assertContains(response, f'P-W{i}')
        self.assertContains(response, 'id="warn-pager"')
        self.assertContains(response, '共 <span id="warn-total">9</span> 条')


class ProjectStatisticsDashboardTests(DashboardFixtureMixin, TestCase):
    def _json(self, **params):
        params['format'] = 'json'
        response = self.client.get(reverse('project_statistics'), params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_empty_payload_keeps_zero_keys(self):
        data = self._json(start_date='1990-01-01', end_date='1990-01-02')
        self.assertEqual(data['total_projects'], 0)
        self.assertEqual(set(data['stats']), set(STAT_KEYS))
        self.assertTrue(all(value == 0 for value in data['stats'].values()))
        self.assertTrue(all(value == 0.0 for value in data['analysis'].values()))

    def test_awaiting_approval_counts_once_as_in_development(self):
        project = self._project('P-APPR')
        project.nodes.filter(stage=ProjectStage.RND).update(status='AWAITING_APPROVAL')
        data = self._json()
        self.assertEqual(data['total_projects'], 1)
        self.assertEqual(data['stats']['in_development'], 1)
        self.assertEqual(sum(data['stats'].values()), 1)

    def test_mass_production_does_not_also_count_as_in_development(self):
        project = self._project('P-MASS')
        project.nodes.filter(stage=ProjectStage.MASS_PROD).update(status='DONE')
        data = self._json()
        self.assertEqual(data['stats']['mass_production_completed'], 1)
        self.assertEqual(data['stats']['in_development'], 0)
        self.assertEqual(sum(data['stats'].values()), 1)

    def test_rates_keep_two_decimal_places(self):
        done = self._project('P-R1')
        done.nodes.filter(stage=ProjectStage.MASS_PROD).update(status='DONE')
        self._project('P-R2')
        self._project('P-R3')
        data = self._json()
        self.assertEqual(data['analysis']['pass_rate'], 33.33)
        self.assertEqual(data['analysis']['mass_prod_rate'], 33.33)
        self.assertEqual(data['analysis']['feedback_rate'], 0.0)
        self.assertEqual(data['analysis']['pause_rate'], 0.0)
        self.assertEqual(data['analysis']['termination_rate'], 0.0)

    def test_page_title(self):
        response = self.client.get(reverse('project_statistics'))
        self.assertContains(response, '项目统计看板')
        self.assertContains(response, '{y:.2f}%')
