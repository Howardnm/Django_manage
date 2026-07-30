from django.shortcuts import render
from django.views import View

from app_panel.mixins import (
    PanelAccessMixin,
    WorkspaceFormCardMixin,
    WorkspaceWorkflowCardMixin,
)

MAX_ITEMS = 5  # 每张卡片最多展示的记录数


class PersonalWorkspaceView(PanelAccessMixin, View):
    """个人工作台：当前用户的表单、流程、待办、已办概览。

    L1/L2: PanelAccessMixin (module_code='panel') 从 DB 读取。
    L3: 显式声明 [] — 跨模块聚合视图，卡片级鉴权由 Workspace*CardMixin 在 get() 中执行。
    """

    permission_required = []  # 跨模块聚合，卡片级鉴权在 get() 中执行

    def get(self, request):
        user = request.user
        context = {}

        # ── 卡片级权限检查（由 app_panel/mixins.py 统一管理）──
        has_form = WorkspaceFormCardMixin.user_has_form_access(user)
        has_workflow = WorkspaceWorkflowCardMixin.user_has_workflow_access(user)

        # ── Auth-Before-Query：仅对通过鉴权的模块查询 ──
        if has_form:
            from app_form_management.models import FormSubmission

            # 草稿（最近 5 条，按更新时间倒序）
            context['recent_drafts'] = (
                FormSubmission.objects
                .filter(submitted_by=user, status='DRAFT')
                .select_related('template')
                .order_by('-updated_at')[:MAX_ITEMS]
            )
            context['draft_count'] = (
                FormSubmission.objects.filter(submitted_by=user, status='DRAFT').count()
            )

            # 已提交（最近 5 条）
            context['recent_submissions'] = (
                FormSubmission.objects
                .filter(submitted_by=user, status='SUBMITTED')
                .select_related('template', 'workflow_instance__definition')
                .order_by('-created_at')[:MAX_ITEMS]
            )
            context['submission_count'] = (
                FormSubmission.objects.filter(submitted_by=user, status='SUBMITTED').count()
            )

        if has_workflow:
            from app_workflow.models import WorkflowInstance, WorkflowTask

            # 我发起的流程（最近 5 条）
            context['recent_instances'] = (
                WorkflowInstance.objects
                .filter(started_by=user)
                .select_related('definition')
                .prefetch_related('tasks')
                .order_by('-started_at')[:MAX_ITEMS]
            )
            context['initiated_count'] = (
                WorkflowInstance.objects.filter(started_by=user).count()
            )

            # 待办任务（最近 5 条）
            context['pending_tasks'] = (
                WorkflowTask.objects
                .filter(assigned_to=user, status='PENDING')
                .select_related('instance__definition', 'instance__started_by')
                .order_by('-created_at')[:MAX_ITEMS]
            )
            context['pending_count'] = (
                WorkflowTask.objects.filter(
                    assigned_to=user, status='PENDING'
                ).count()
            )

            # 已办任务（最近 5 条）
            context['completed_tasks'] = (
                WorkflowTask.objects
                .filter(
                    assigned_to=user,
                    status__in=['COMPLETED', 'REJECTED', 'CANCELED']
                )
                .select_related('instance__definition')
                .order_by('-completed_at')[:MAX_ITEMS]
            )
            context['completed_count'] = (
                WorkflowTask.objects.filter(
                    assigned_to=user,
                    status__in=['COMPLETED', 'REJECTED', 'CANCELED']
                ).count()
            )

        context['has_form'] = has_form
        context['has_workflow'] = has_workflow
        return render(request, 'apps/app_panel/personal_workspace.html', context)
