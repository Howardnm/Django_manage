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
