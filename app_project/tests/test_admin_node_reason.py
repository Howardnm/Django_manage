"""Admin 项目进度节点行内表：按节点类型显示原因下拉。"""
from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from app_project.admin import ProjectNodeInline
from app_project.models import (
    FailureReason, FeedbackType, Project, ProjectNode, ProjectStage,
)

User = get_user_model()


def _make_user(username):
    return User.objects.create_user(username=username, email=f'{username}@test.local', password='x')


def _node_form(node, reason=''):
    request = RequestFactory().get('/admin/app_project/project/1/change/')
    request.user = User.objects.create_superuser(
        f'admin-{node.pk}', f'admin-{node.pk}@test.local', 'x',
    )
    form_class = ProjectNodeInline(Project, admin.site).get_formset(request, node.project).form
    data = {
        'stage': node.stage,
        'status': node.status,
        'round': node.round,
        'order': node.order,
        'final_score': node.final_score,
        'remark': node.remark or '',
        'reason': reason,
    }
    return form_class(data=data, instance=node)


class ProjectNodeInlineReasonTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name='原因项目', manager=_make_user('reason-mgr'))
        self.node = self.project.nodes.get(stage=ProjectStage.RND)
        self.node.remark = ''
        self.node.save()
        self.active_failure = FailureReason.objects.create(name='色差', order=1)
        self.inactive_failure = FailureReason.objects.create(name='旧异常', is_active=False, order=2)
        self.unused_failure = FailureReason.objects.create(name='停用未选', is_active=False, order=3)
        self.active_feedback = FeedbackType.objects.create(name='调色', order=1)
        self.inactive_feedback = FeedbackType.objects.create(name='旧意见', is_active=False, order=2)
        self.unused_feedback = FeedbackType.objects.create(name='停用意见', is_active=False, order=3)

    def _choice_ids(self, form):
        return set(form.fields['reason'].queryset.values_list('pk', flat=True))

    def test_failed_node_saves_failure_reason_only(self):
        self.node.status = 'FAILED'
        self.node.feedback_type = self.active_feedback
        self.node.failure_reason = self.inactive_failure
        self.node.save()

        form = _node_form(self.node, reason=str(self.active_failure.pk))
        self.assertIsInstance(form.fields['reason'], forms.ModelChoiceField)
        self.assertEqual(form.fields['reason'].queryset.model, FailureReason)
        ids = self._choice_ids(form)
        self.assertIn(self.active_failure.pk, ids)
        self.assertIn(self.inactive_failure.pk, ids)
        self.assertNotIn(self.unused_failure.pk, ids)

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.node.refresh_from_db()
        self.assertEqual(self.node.failure_reason_id, self.active_failure.pk)
        self.assertEqual(self.node.feedback_type_id, self.active_feedback.pk)

    def test_failed_status_wins_over_feedback_stage(self):
        self.node.stage = ProjectStage.FEEDBACK
        self.node.status = 'FAILED'
        self.node.save()
        form = _node_form(self.node)
        self.assertEqual(form.fields['reason'].queryset.model, FailureReason)

    def test_feedback_status_saves_feedback_type_only(self):
        self.node.status = 'FEEDBACK'
        self.node.failure_reason = self.active_failure
        self.node.feedback_type = self.inactive_feedback
        self.node.save()

        form = _node_form(self.node, reason=str(self.active_feedback.pk))
        self.assertEqual(form.fields['reason'].queryset.model, FeedbackType)
        ids = self._choice_ids(form)
        self.assertIn(self.active_feedback.pk, ids)
        self.assertIn(self.inactive_feedback.pk, ids)
        self.assertNotIn(self.unused_feedback.pk, ids)

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.node.refresh_from_db()
        self.assertEqual(self.node.feedback_type_id, self.active_feedback.pk)
        self.assertEqual(self.node.failure_reason_id, self.active_failure.pk)

    def test_feedback_stage_uses_feedback_type(self):
        feedback = ProjectNode.objects.create(
            project=self.project, stage=ProjectStage.FEEDBACK, status='PENDING',
            order=99, remark='',
        )
        form = _node_form(feedback, reason=str(self.active_feedback.pk))
        self.assertEqual(form.fields['reason'].queryset.model, FeedbackType)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        feedback.refresh_from_db()
        self.assertEqual(feedback.feedback_type_id, self.active_feedback.pk)

    def test_other_node_renders_dash_and_keeps_reasons(self):
        self.node.failure_reason = self.active_failure
        self.node.feedback_type = self.active_feedback
        self.node.save()

        form = _node_form(self.node, reason=str(self.active_failure.pk))
        self.assertNotIsInstance(form.fields['reason'], forms.ModelChoiceField)
        self.assertTrue(form.fields['reason'].disabled)
        self.assertIn('—', str(form['reason']))

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.node.refresh_from_db()
        self.assertEqual(self.node.failure_reason_id, self.active_failure.pk)
        self.assertEqual(self.node.feedback_type_id, self.active_feedback.pk)
